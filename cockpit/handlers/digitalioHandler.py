#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2021 University of Oxford
## Copyright (C) 2023 Ian Dobbie ian.dobbie@jhu.edu
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

from cockpit.handlers import deviceHandler
from cockpit import depot
import cockpit.gui
import wx
import cockpit.util.threads

# class Filter:
#     """An individual filter."""

#     def __init__(self, position, *args):
#         self.position = int(position)
#         # args describes the filter.
#         # The description can be one of
#         #   label, value
#         #   (label, value)
#         #   label
#         if isinstance(args[0], tuple):
#             self.label = args[0][0]
#             if len(args[0]) > 1:
#                 self.value = args[0][1]
#             else:
#                 self.value = None
#         else:
#             self.label = args[0]
#             if len(args) > 1:
#                 self.value = args[1]
#             else:
#                 self.value = None

            
#     def __repr__(self):
#         if self.value:
#             return '%d: %s, %s' % (self.position, self.label, self.value)
#         else:
#             return '%d: %s' % (self.position, self.label)


class DigitalIOHandler(deviceHandler.DeviceHandler):
    """A handler for Digital IO devcies."""
    def __init__(self, name, groupName, callbacks):
        super().__init__(name, groupName, callbacks)

    def onSaveSettings(self):
        return self.callbacks['getOutputs']()

    def onLoadSettings(self, settings):
        print ("onLoad:",settings)
        return self.callbacks['getOutputs'](settings)

       ### UI functions ###
    def makeUI(self, parent):
        self.panel = wx.Panel(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.pathNameToButton={}
        for key in self.paths.keys():
            button = wx.ToggleButton(self.panel, wx.ID_ANY)
            button.SetLabel(key)
            button.Bind(wx.EVT_TOGGLEBUTTON,
                        lambda evt,b=button: self.togglePaths(b))
            sizer.Add(button, 1, wx.EXPAND)
            self.pathNameToButton[key]=button
        self.panel.SetSizerAndFit(sizer)
        return self.panel

    def togglePaths(self,button):
        path=button.Label
        if button.GetValue():
            #button is active so set the relevant DIO lines
            #take settings for this path
            settings=self.paths[path]
            for object in settings.keys():
                #loop through settings and set each named object to that state.
                self.write_line(self.labels.index(object),
                                settings[object])
                print(path,self._proxy.read_all_lines())
            #Need some way to define exclusive and non-exclusive paths
            #assume they are exclusive for now.
            for key in self.pathNameToButton.keys():
                if(key!=path):
                    self.pathNameToButton[key].SetValue(False)

    @cockpit.util.threads.callInMainThread
    def updateAfterChange(self,*args):
#        # Accept *args so that can be called directly as a Pyro callback
#        # or an event handler.
        pass
#        # need to update display if active.
#self.


def finalizeInitialization(self):
        self.updateAfterChange()