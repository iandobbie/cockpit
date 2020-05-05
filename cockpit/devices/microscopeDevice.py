#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.


"""Microscope devices.

   Supports devices that implement the interface defined in
   microscope.devices

For a direct connection::

    [device]
    type: cockpit.devices.a_module.SomeClass
    uri: PYRO:SomeDevice@host.port

For connection via a controller::

    [device]
    type: cockpit.devices.a_module.SomeClass
    controller: some_controller
    controller.name: remote_device    # optional

    [some_controller]
    type: cockpit.devices.another_module.AnotherClass
    uri: PYRO:SomeControler@host.port

"""

import typing

import Pyro4
import wx
from cockpit import events
from cockpit.devices import device
from cockpit.devices import stage
from cockpit import depot
import cockpit.devices.stage
import cockpit.gui.device
import cockpit.handlers.deviceHandler
import cockpit.handlers.filterHandler
import cockpit.handlers.lightPower
import cockpit.handlers.lightSource
import cockpit.util.colors
import cockpit.util.userConfig
import cockpit.util.threads
from cockpit.gui.device import SettingsEditor
import re
import threading
import time

from microscope.devices import AxisLimits

# Pseudo-enum to track whether device defaults in place.
(DEFAULTS_NONE, DEFAULTS_PENDING, DEFAULTS_SENT) = range(3)

class MicroscopeBase(device.Device):
    """A class to communicate with the UniversalDevice interface."""
    def __init__(self, name, config):
        super().__init__(name, config)
        self.handlers = []
        self.panel = None
        # Pyro proxy
        self._proxy = None
        self.settings = {}
        self.cached_settings={}
        self.settings_editor = None
        self.defaults = DEFAULTS_NONE
        self.enabled = True
        # Placeholders for methods deferred to proxy.
        self.get_all_settings = None
        self.get_setting = None
        self.set_setting = None
        self.describe_setting = None
        self.describe_settings = None

    def initialize(self):
        super().initialize()
        # Connect to the proxy.
        if 'controller' not in self.config:
            self._proxy = Pyro4.Proxy(self.uri)
        else:
            c = depot.getDeviceWithName(self.config['controller'])
            c_name = self.config.get('controller.name', None)
            if c_name is not None:
                try:
                    self._proxy = c._proxy.devices[c_name]
                except:
                    raise Exception("%s: device not found on controller '%s'." % (self.name, c.name))
            elif len(c._proxy.devices) == 0:
                raise Exception("%s: no devices found on controller." % self.name)
            elif len(c._proxy.devices) == 1:
                    self._proxy = next(iter(c._proxy.devices.values()))
            else:
                 raise Exception("%s: More than one device found on controller, "\
                                 "so must specify controller.name." % self.name)
        self.get_all_settings = self._proxy.get_all_settings
        self.get_setting = self._proxy.get_setting
        self.set_setting = self._proxy.set_setting
        self.describe_setting = self._proxy.describe_setting
        self.describe_settings = self._proxy.describe_settings

    def finalizeInitialization(self):
        super().finalizeInitialization()
        # Set default settings on remote device. These will be over-
        # ridden by any defaults in userConfig, later.
        # Currently, settings are an 'advanced' feature --- the remote
        # interface relies on us to send it valid data, so we have to
        # convert our strings to the appropriate type here.
        ss = self.config.get('settings')
        settings = {}
        if ss:
            settings.update(([m.groups() for kv in ss.split('\n')
                             for m in [re.match(r'(.*)\s*[:=]\s*(.*)', kv)] if m]))
        for k,v in settings.items():
            try:
                desc = self.describe_setting(k)
            except:
                print ("%s ingoring unknown setting '%s'." % (self.name, k))
                continue
            if desc['type'] == 'str':
                pass
            elif desc['type'] == 'int':
                v = int(v)
            elif desc['type'] == 'float':
                v = float(v)
            elif desc['type'] == 'bool':
                v = v.lower() in ['1', 'true']
            elif desc['type'] == 'tuple':
                print ("%s ignoring tuple setting '%s' - not yet supported." % (self.name, k))
                continue
            elif desc['type'] == 'enum':
                if v.isdigit():
                    v = int(v)
                else:
                    vmap = dict((k,v) for v,k in desc['values'])
                    v = vmap.get(v, None)
                if v is None:
                    print ("%s ignoring enum setting '%s' with unrecognised value." % (self.name, k))
                    continue
            self.set_setting(k, v)
        self._readUserConfig()


    def getHandlers(self):
        """Return device handlers. Derived classes may override this."""
        result = cockpit.handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handlers = [result]
        return [result]


    def showSettings(self, evt):
        if not self.settings_editor:
            # TODO - there's a problem with abstraction here. The settings
            # editor needs the describe/get/set settings functions from the
            # proxy, but it also needs to be able to invalidate the cache
            # on the handler. The handler should probably expose the
            # settings interface.
            self.setAnyDefaults()
            import collections.abc
            if self.handlers and isinstance(self.handlers, collections.abc.Sequence):
                h = self.handlers[0]
            elif self.handlers:
                h = self.handlers
            else:
                h = None
            parent = evt.EventObject.Parent
            self.settings_editor = SettingsEditor(self, parent, handler=h)
            self.settings_editor.Show()
        self.settings_editor.SetPosition(wx.GetMousePosition())
        self.settings_editor.Raise()


    def updateSettings(self, settings=None):
        if settings is not None:
            self._proxy.update_settings(settings)
        self.settings.update(self._proxy.get_all_settings())
        events.publish(events.SETTINGS_CHANGED % str(self))


    def setAnyDefaults(self):
        # Set any defaults found in userConfig.
        if self.defaults != DEFAULTS_PENDING:
            # nothing to do
            return
        try:
            self._proxy.update_settings(self.settings)
        except Exception as e:
            print (e)
        else:
            self.defaults = DEFAULTS_SENT


    def _readUserConfig(self):
        idstr = self.name + '_SETTINGS'
        defaults = cockpit.util.userConfig.getValue(idstr)
        if defaults is None:
            self.defaults = DEFAULTS_NONE
            return
        self.settings.update(defaults)
        self.defaults = DEFAULTS_PENDING
        self.setAnyDefaults()


    def prepareForExperiment(self, name, experiment):
        """Make the hardware ready for an experiment."""
        self.cached_settings.update(self.settings)


class MicroscopeGenericDevice(MicroscopeBase):
    def getHandlers(self):
        """Return device handlers."""
        result = cockpit.handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handlers = [result]
        return [result]


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        adv_button = cockpit.gui.device.Button(parent=self.panel,
                                       label=self.name,
                                       leftAction=self.showSettings)
        sizer.Add(adv_button)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


class MicroscopeSwitchableDevice(MicroscopeBase):
    def getHandlers(self):
        """Return device handlers."""
        result = cockpit.handlers.deviceHandler.DeviceHandler(
            "%s" % self.name, "universal devices",
            False,
            {'makeUI': self.makeUI},
            depot.GENERIC_DEVICE)
        self.handlers = [result]
        return [result]


    ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        adv_button = cockpit.gui.device.Button(parent=self.panel,
                                       label=self.name,
                                       leftAction=self.showSettings)
        sizer.Add(adv_button)
        self.panel.SetSizerAndFit(sizer)
        return self.panel


    def finalizeInitialization(self):
        super().finalizeInitialization()
        self.enabled = self._proxy.get_is_enabled()


class MicroscopeLaser(MicroscopeBase):
    """A light source with power control.

    Sample config entry:
      [488nm]
      type: MicroscopeLaser
      uri: PYRO:DeepstarLaser@192.168.0.2:7001
      wavelength: 488
      triggerSource: trigsource
      triggerLine: 1

      [trigsource]
      type: ExecutorDevice
      ...
    """
    def _setEnabled(self, on):
        if on:
            self._proxy.enable()
        else:
            self._proxy.disable()

    def getHandlers(self):
        """Return device handlers. Derived classes may override this."""
        # Querying remote for maxPower can cause delays, so set to None
        # and update later.
        self.handlers.append(cockpit.handlers.lightPower.LightPowerHandler(
            self.name + ' power',  # name
            self.name + ' light source',  # groupName
            {
                'setPower': cockpit.util.threads.callInNewThread(self._proxy.set_power_mw),
                'getPower': self._proxy.get_power_mw, # Synchronous - can hang threads.
            },
            self.config.get('wavelength', None),
            0, None, 20, #minPower, maxPower, curPower,
            isEnabled=True))
        trigsource = self.config.get('triggersource', None)
        trigline = self.config.get('triggerline', None)
        if trigsource:
            trighandler = depot.getHandler(trigsource, depot.EXECUTOR)
        else:
            trighandler = None
        self._exposureTime = 100
        self.handlers.append(cockpit.handlers.lightSource.LightHandler(
            self.name,
            self.name + ' light source',
            {'setEnabled': lambda name, on: self._setEnabled(on),
             'setExposureTime': lambda name, value: setattr(self, '_exposureTime', value),
             'getExposureTime': lambda name: self._exposureTime},
            self.config.get('wavelength', None),
            100,
            trighandler,
            trigline))

        return self.handlers


    def finalizeInitialization(self):
        # This should probably work the other way around:
        # after init, the handlers should query for the current state,
        # rather than the device pushing state info to the handlers as
        # we currently do here.
        #
        # Query the remote to update max power on handler.
        ph = self.handlers[0] # powerhandler
        ph.setMaxPower(self._proxy.get_max_power_mw())
        ph.powerSetPoint = self._proxy.get_set_power_mw()
        # Set lightHandler to enabled if light source is on.
        lh = self.handlers[-1]
        lh.state = int(self._proxy.get_is_on())


class MicroscopeFilter(MicroscopeBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cameras
        cdefs = self.config.get('cameras', None)
        if cdefs:
            self.cameras = re.split('[,;]\s*', cdefs)
        else:
            self.cameras = None

        # Lights
        ldefs = self.config.get('lights', None)
        if ldefs:
            self.lights = re.split('[,;]\s*', ldefs)
        else:
            self.lights = None

        # Filters
        # Used to do this in finalizeInitialization, but there's
        # no obvious reason to do it there, and it occasionally
        # caused a threadpool deadlock.
        fdefs = self.config.get('filters', None)
        if fdefs:
            fdefs = [re.split(':\s*|,\s*', f) for f in re.split('\n', fdefs) if f]
        else:
            fdefs = self._proxy.get_filters()
        if not fdefs:
            raise Exception ("No local or remote filter definitions for %s." % self.name)
        self.filters = [cockpit.handlers.filterHandler.Filter(*f) for f in fdefs]


    def getHandlers(self):
        """Return device handlers."""
        h = cockpit.handlers.filterHandler.FilterHandler(self.name, 'filters', False,
                                                 {'setPosition': self.setPosition,
                                                  'getPosition': self.getPosition,
                                                  'getFilters': self.getFilters},
                                                 self.cameras,
                                                 self.lights)
        self.handlers = [h]
        return self.handlers


    def setPosition(self, position, callback=None):
        asproxy = Pyro4.Proxy(self._proxy._pyroUri)
        asproxy._pyroAsync()
        result = asproxy.set_setting('position', position).then(callback)


    def getPosition(self):
        return self._proxy.get_setting('position')


    def getFilters(self):
        return self.filters


class MicroscopeStageAxis:
    def __init__(self, axis:, index: int, primitives: typing.List[str]):
        self._axis = axis # this will probably be a Pyro proxy
        self._index = index
        # FIXME: the primitives is actually a property of the stage
        # but the way cockpit is designed this is read from a
        # PositionerHandler which is a single axis.
        self._primitives = primitives

        # By default, soft limits are the hard limits
        self._soft_limits = self._axis.limits

    def getHandler(self, stage_name: str):
        name = "%d %s" % (self._index, stage_name)
        group_name = "%d stage motion" % self._index
        eligible_for_experiments = False
        callbacks = {
            'getMovementTime' : self.getMovementTime,
            'getPosition' : self.getPosition,
            'getPrimitives' : self.getPrimitives,
            'moveAbsolute' : self.moveAbsolute,
            'moveRelative' : self.moveRelative,
            'setSafety' : self.setSafety,
        }
        step_sizes = [.1, .2, .5, 1, 2, 5, 10, 50, 100, 500, 1000, 5000]
        step_index = 3

        return cockpit.handlers.stagePositioner.PositionerHandler(name,
                                                                  group_name,
                                                                  eligible_for_experiments,
                                                                  callbacks,
                                                                  self._index,
                                                                  step_sizes,
                                                                  step_index,
                                                                  self._axis.limits,
                                                                  self._soft_limits)


    #
    # FIXME: we need some sort of factor to adjust from microscope
    # unit to microns!!!!
    #

    def getMovementTime(self, axis: int, start: float, end: float):
        pass

    def getPosition(self, axis: int) -> float:
        """Get the position for the specified axis."""
        return self._axis.position

    def getPrimitives(self) -> typing.List[str]:
        return self._primitives

    def moveAbsolute(self, axis: int, position: float) -> None:
        """Move axis to the given position in microns."""
        if self._soft_limits.lower < position < self._soft_limits.upper:
            self._axis.move_to(position)
        # TODO: are we supposed to publish events about the movement?
        # Other devices seem to do it via the sendXYPositionUpdates.

    def moveRelative(self, axis: int, delta: float) -> None:
        """Move the axis by the specified delta, in microns."""
        position = self._axis.position + delta
        if self._soft_limits.lower < position < self._soft_limits.upper:
            self._axis.move_by(delta)
        # TODO: are we supposed to publish events about the movement?
        # Other devices seem to do it via the sendXYPositionUpdates.

    def setSafety(self, axis: int, value: float, isMax: bool):
        """Set the min or max soft safety limit."""
        # TODO: add some check that soft limits are not beyond the
        # hard limits or somehow swapped.
        if isMax:
            self._soft_limits = AxisLimits(self._soft_limits.lower, value)
        else:
            self._soft_limits = AxisLimits(value, self._soft_limits.upper)



class MicroscopeStage(cockpit.devices.stage.StageDevice, MicroscopeBase):
    """A class to control remote python microscope.

    Sample config entry:
      [XYStage]
      type: MicroscopeXYStage
      uri: PYRO:XYStage@192.168.0.2:7001
      ...
    """

    def __init__(self, name: str, config: typing.Mapping[str, str]) -> None:
        super().__init__(name, config)

        # FIXME: we should not cache because stage might have moved without us
        ## Cached copy of the stage's position. Initialized to an impossible
        # value; this will be modified in initialize.
        #        self.xyPositionCache = (10 ** 100, 10 ** 100)
        ## Target positions for movement in X and Y, or None if that axis is
        # not moving.
        #        self.xyMotionTargets = [None, None]

        self._axis_to_name = {} # type: typing.Dict[int, str]
        for i, axis in enumerate('xyz'):
            config_name = axis + '-axis-name'
            if config_name in config:
                self._axis_to_name[i] = config['config_name']

        ##followojng two need to come from config file
        ## Maps the cockpit's axis ordering (0: X, 1: Y, 2: Z) to the
        # XY stage's ordering (1: Y, 0: X)
        self.axisMapper = {0: 'x', 1: 'y'}
        ## Maps cockpit axis ordering to a +-1 multiplier to apply to motion,
        # since some of our axes are flipped.
        self.axisSignMapper = {0: -1, 1: 1}

    def initialize(self):
        super().initialize()
        # Enabling the stage might cause it to move to home.
        self._proxy.enable()

        # check that all axis names are valid

        # should we also be checking that we can control all axis and
        # maybe raise a warning?

        name_to_axis = {v:k for k,v in self._axis_to_name}

        # By default, soft limits are the hard limits.
        hard_limits = self._proxy.limits
#        self._soft_limits = {i, hard_limits[n
        try:
            #Limits have to come from config as some stages
            #eg PriorProScanIII can only find limits by moving to them
            #and we dont want to do that every init.
            #this ought to be replaces with a AxisLimits named tuple,
            #but to get it workjing here I am fdoing this. IMD 20200420
            limits = self._proxy.limits
            self.softlimits=[[limits['x'].lower,limits['y'].lower],
                             [limits['x'].upper,limits['y'].upper]]
        except:
            print ("Microscope Stage no limits section setting default.")
            self.softlimits=[[-10000,-10000],[10000,10000]]

        # Get the proper initial position.
        self.getXYPosition(shouldUseCache = False)


    def getHandlers(self):
        self._axes = [] # type: typing.List[MicroscopeStageAxis]
        for index, axis_name in self._axis_to_name.items():
            self._axes.append(MicroscopeStageAxis(self._proxy.axes[axis_name],
                                                  index, self._primitives))

        return [axis.getHandler(self.name) for axis in self._axes]

    def moveXYAbsolute(self,axis, pos):
        with self.xyLock:
            if self.xyMotionTargets[axis] is not None:
                # Don't stack motion commands for the same axis
                return
        self.xyMotionTargets[axis] = pos
#        if not self.isMotionSafe(axis):
#            self.xyMotionTargets[axis] = None
#            raise RuntimeError("Moving axis %d to %s would pass through unsafe zone" % (axis, pos))
        self._proxy.move_to({self.axisMapper[axis]:
                             self.axisSignMapper[axis] * pos })
        self.sendXYPositionUpdates()

    def moveXYRelative(self, axis, delta):
        if not delta:
            # Received a bogus motion request.
            return
        curPos = self.xyPositionCache[axis]
        self.xyMotionTargets[axis] = curPos+delta
        self._proxy.move_to({self.axisMapper[axis]: axisSignMapper[axis]*(curPos + delta)})
        self.sendXYPositionUpdates()


    def getXYPosition(self, axis = None, shouldUseCache = True):
        if not shouldUseCache:
            pos = self._proxy.position
            # Positions are in millimeters, and we need microns.
            x = float(pos[self.axisMapper[0]]) * self.axisSignMapper[0]
            y = float(pos[self.axisMapper[1]]) * self.axisSignMapper[1]
            self.xyPositionCache = (x, y)
        if axis is None:
            return self.xyPositionCache
        return self.xyPositionCache[axis]
