#!/usr/bin/env python
# -*- coding: utf-8 -*-

from cockpit import depot
from cockpit import events
from cockpit.experiment import immediateMode

import cockpit.interfaces.imager as imager
import cockpit.interfaces.stageMover

# import cockpit.util.user
import wx
import os
import time
import numpy as np
import imageio

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = "BiasImageDatasetExperiment"
CAMERA_TIMEOUT = 2.0


class BiasImageDatasetExperiment(immediateMode.ImmediateModeExperiment):
    """Create BiasImageDatasetExperiment from parent class (the ImmediateModeExperiment)
    Potentially we should directly create an Experiment, for ActionTable efficiency reasons,
    but this should be a good starting point
    We are using a composite AO device for applying a sequence of aberrations"""

    def __init__(
        self,
        *args,
        bias_modes=(4, 5, 6, 7, 10),
        abb_magnitude=5,
        applied_modes=(4, 5, 6, 7, 10),
        applied_step=5,
        numReps=1,
        initial_abb=None,
        repDuration=4,
        imagesPerRep=1,
        saveprefix="BIDE_",
        savePath="",
        **kwargs,
    ):
        areas = numReps
        self.bias_modes = bias_modes  # 0-indexed-Noll
        print(bias_modes)
        applied_steps = np.linspace(-abb_magnitude, abb_magnitude, applied_step)

        self.abb_generator = self.generateAbb(
            bias_modes, applied_modes, applied_steps, areas
        )  # Not going to be thread safe
        try:
            self.saveBasePath = os.path.join(cockpit.util.userConfig.getValue("data-dir"), saveprefix)
        except:
            self.saveBasePath = os.path.join(os.path.expanduser("~"), saveprefix)

        self.numReps = len(applied_steps) * areas

        # Set savepath to '' to prevent saving images. We will save our own images,
        # because setting filenames using Experiment/DataSaver look like it is
        # going to require a bunch of complicated subclassing
        super().__init__(self.numReps, repDuration, imagesPerRep, savePath="")

        # override cameraToImageCount so bias images are correctly saved to individual files
        # (necessary if using DataSaver)
        self.cameraToImageCount = 2 * len(bias_modes) + 1

        self.table = None  # Apparently we need this, even though we're not using it? suspect there is a problem with ImmediateModeExperiment
        self.time_start = time.time()

    def is_running(self):
        # HACK: Imager won't collect images if an experiment is running... Catch 22 here... So just breaking this for now
        return False

    def executeRep(self, repNum):
        print(f"Started rep {repNum+1}/{self.numReps} Time Elapsed: {time.time()-self.time_start:.1f}")
        # Assume correct camera already active
        activeCams = depot.getActiveCameras()
        camera = activeCams[0]

        aodev = depot.getDeviceWithName("dm")  # IS THIS THE CORRECT DEVICE NAME?

        try:
            offset = aodev.proxy.get_system_flat()  # assumes the correction for flat has already been done.
        except:
            print("Failed to Get system flat")
            offset = None

        try:
            aodev.proxy.get_controlMatrix()

        except:
            print("Failed to Get Control Matrix: Please Calibrate DM")
            aodev.proxy.set_controlMatrix(np.zeros((aodev.no_actuators, 61)))
            print("Set fake control matrix")

        biaslist, fprefix, newarea = self.abb_generator.__next__()
        imlist = []
        dm_set_failure = False

        for abb in biaslist:
            try:
                aodev.proxy.set_phase(abb, offset)
            except:
                dm_set_failure = True

            # Do we need a pause here?
            # Collect image
            # takeimage = wx.GetApp().Imager.takeImage # this allows for blocking
            takeimage = depot.getHandlerWithName(f"{camera.name} imager").takeImage
            result = events.executeAndWaitForOrTimeout(
                events.NEW_IMAGE % camera.name,
                takeimage,
                camera.getExposureTime() / 1000 + CAMERA_TIMEOUT,
                # shouldBlock=True,
            )
            if result is not None:
                imlist.append(result[0])
            else:
                raise TimeoutError("Image capture returned None")

        if dm_set_failure:
            print("Didn't set the aberration on the DM")
        # Save image - would be better to use existing DataSaver, but doesn't seem to allow custom naming scheme
        filename = f"{self.saveBasePath}{fprefix}.tif"

        imageio.mimwrite(filename, imlist, format="tif")

        # Get the current stage position; positions are in microns.
        curX, curY, curZ = cockpit.interfaces.stageMover.getPosition()

        # Move to a new XY position if completed scan through all applied steps.
        if newarea:
            cockpit.interfaces.stageMover.goToXY((curX + 50, curY - 50), shouldBlock=True)

        if self.numReps == repNum + 1:
            print("-----Experiment Complete-----")

    def makeBiasPolytope(self, start_aberrations, offset_axes, nk, steps=(1,)):
        """Return list of list of zernike amplitudes ('betas') for generating cross-polytope pattern of psfs
        """
        # beta (diffraction-limited), N_beta = cpsf.czern.nk
        beta = np.zeros(nk, dtype=np.float32)
        beta[:] = start_aberrations

        # add offsets to beta

        betas = []
        betas.append(tuple(beta))
        for axis in offset_axes:
            for step in steps:
                plus_offset = beta.copy()
                plus_offset[axis] += 1 * step
                betas.append(tuple(plus_offset))
            for step in steps:
                minus_offset = beta.copy()
                minus_offset[axis] -= 1 * step
                betas.append(tuple(minus_offset))

        return betas

    def generateAbb(self, bias_modes, applied_modes, applied_steps, areas):
        """Returns each list of bias aberrations for AO device to apply"""
        start_aberrations = np.zeros(np.max((np.max(bias_modes), (np.max(applied_modes)))) + 1)
        newarea = False
        for area in range(areas):
            for applied_abb in applied_modes:
                for step in applied_steps:
                    start_aberrations[applied_abb] = step
                    biaslist = self.makeBiasPolytope(start_aberrations, bias_modes, len(start_aberrations))
                    fprefix = f"A{area}A{applied_abb}S{step:.1f}_"
                    yield biaslist, fprefix, newarea
                    newarea = False
            newarea = True


EXPERIMENT_CLASS = BiasImageDatasetExperiment  # Don't know what the point of this is but is required by GUI
