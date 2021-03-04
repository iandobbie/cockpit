.. Copyright (C) 2020 David Miguel Susano Pinto <david.pinto@bioch.ox.ac.uk> (C) 2021 Martin Hailstone
   Permission is granted to copy, distribute and/or modify this
   document under the terms of the GNU Free Documentation License,
   Version 1.3 or any later version published by the Free Software
   Foundation; with no Invariant Sections, no Front-Cover Texts, and
   no Back-Cover Texts.  A copy of the license is included in the
   section entitled "GNU Free Documentation License".


Configuration
*************

Cockpit is based on `microscope <https://www.micron.ox.ac.uk/software/microscope/>`_, which handles the hardware level device communication. This page is concerned with the configuration of cockpit proper: it assumes you already have a working microscope ``device_server``. For more information on setting up a ``device_server`` see `here <https://www.micron.ox.ac.uk/software/microscope/doc/architecture/device-server.html>`_

There are two parts to configuring cockpit. The :ref:`configuration
of cockpit proper <cockpit-config>` that covers most of cockpit
options, and the :ref:`depot configuration <depot-config>` which lists
all devices that cockpit will have control over.

Configuring Cockpit for the first time
======================================

If you've just installed cockpit through ``pip`` and run it, you'll be running it without these configuration files. You will need to make your own, but it is probably easiest to use someone else's config files as a starting point. Example configuration files can be found `here <https://github.com/MicronOxford/configs>`_. It is possible to specify just a depot file, provided it is found in the correct :ref:`location <_default_config_locations>`.

- Create a  ``depot.conf`` :ref:`file <depot-config>`. It is possible to specify just a depot file, provided it is found in the correct location
- Verify that the depot file is working correctly, and devices are connected with ``python -m cockpit.status``
- Further configuration of Cockpit via :ref:`INI file <cockpit-config>`

.. _default_config_locations:

Location of config files
------------------------

By default, Cockpit will look for files named ``cockpit.conf`` and
``depot.conf``.  The location of these files are system-dependent:

=======  =================================  ==========================================
OS       System-wide                        User
=======  =================================  ==========================================
Linux    ``/etc/xdg/cockpit/``              ``$HOME/.config/cockpit/``
MacOS    ``/Library/Preferences/cockpit/``  ``~/Library/Application Support/cockpit/``
Windows  ``%ProgramData%\cockpit\``         ``%LocalAppData%\cockpit\``
=======  =================================  ==========================================


.. _depot-config:

Depot Configuration
===================

Depot is the collection of devices available to the cockpit program.
Each section of a depot configuration specifies a single device: the
section name being the device name, while the options are the device
configuration. These devices should correspond to those defined by your Python Microscope config file.
For example:

.. code:: ini

  [west]
  type: cockpit.devices.microscopeCamera.MicroscopeCamera
  uri: PYRO:WestCamera@127.0.0.1:8001

  [woody]
  type: cockpit.devices.executorDevices.ExecutorDevice
  uri: PYRO:Sheriff@192.168.0.2:8002

  [488nm]
  type: cockpit.devices.microscopeDevice.MicroscopeLaser
  uri: PYRO:Deepstar488Laser@192.168.0.3:7001
  wavelength: 488
  triggerSource: woody
  triggerLine: 1

defines three devices: a camera named "west", an executor named
"woody", and a laser light source named "488nm".  Each device has a
``type`` option which specifies the fully qualified class name of that
device.  Each device type will require a different set of options
which should be documented in the device type documentation.


Multiple files
--------------

Like the cockpit configuration, depot configuration may span multiple
files.  Unlike the cockpit configuration where sections with the same
name are merged, each device section must be unique and sections with
the same name will cause an error, even if in different files.

In the case of depot files, precedence means what files get read.  If
a set of files is present, the others are not processed.  The order is
as follow:

1. depot files in command line options.
2. depot files in cockpit config files.  If multiple cockpit config
   files define depot files, the list of files is read is the one in
   the file with :ref:`highest precedence
   <cockpit_config_precedence>`.
3. ``depot.conf`` files in :ref:`standard, system-dependent locations
   <default_config_locations>`.

.. _cockpit-config:

Cockpit Configuration
=====================

INI file
--------

Cockpit configuration of global settings, directories and logging options is mainly performed with an `INI file
<https://en.wikipedia.org/wiki/INI_file>`_, with multiple options
organised over sections.  For example:

.. code:: ini

  ;; This is a comment.  It's nice to document configuration files.
  [global]
  data-dir: ~/data
  depot-files: /etc/xdg/cockpit/depot/general.conf
               /etc/xdg/cockpit/depot/local.conf
               /etc/xdg/cockpit/depot/experimental.conf

  [log]
  level: info

The following sections and their options are recognised:

global section
--------------

channel-files
  List of files defining channel configurations to be loaded by
  default.  Each file can have any number of channels, later files
  overriding previous channels with the same name.  These files can be
  created via the Channels menu on the menu bar.

config-dir
  Directory for the user configuration file, effectively a cache for
  the last used settings.

data-dir
  Directory for the default location to save image data.

depot-files
  List of files to use for the device depot.  See :ref:`depot-config`.

pyro-pickle-protocol
  Pickle protocol version number to use with Pyro, i.e., when
  connecting to the device server.  Defaults to whatever is already
  set on Pyro which defaults to the highest pickle protocol version
  available.  This affects *all* Pyro connections.

log section
-----------
level
  Threshold level for the messages displayed on both the logging
  window and log files.  Only messages that have a severity level
  equal or higher are displayed.  The severity levels are, by
  increasing order: debug, info, warning, error, and critical.

dir
  Directory to create new log files.

stage section
-------------

primitives

  A list of shapes to draw on stage displays.  Primitives are
  specified by a config entry of the form:

  .. code:: ini

      primitives: c 1000 1000 100
                  r 1000 1000 100 100

  where ``c x0 y0 radius`` defines a circle centred on ``x0, y0`` and
  ``r x0 y0 width height`` defines a rectangle centred on ``x0, y0``.


.. TODO:: Ian says the options for the stage section are historical
          and a fudge.  That need to be changed and may be removed in
          the future.

dishAltitude
  Dish altitude.

slideAltitude
  Slide altitude.

slideTouchdownAltitude
  Slide touchdown altitude.

loadPosition
  Load position used in the touchscreen.

unloadPosition
  Unload position used in the touchscreen.

Command line options
--------------------

Cockpit also takes command line options.  Because these take
precedence over configuration files, they can be used to override
options in the configuration files.  The following command line
options are available:

``--config-file COCKPIT-CONFIG-PATH``
  File path for another cockpit config file.  This option can be
  specified multiple times.  Options defined in later files override
  options in previous ones.

``--no-config-files``
  Skip all configuration files other than those defined via command
  line.  It is equivalent to setting both ``--no-system-config-files``
  and ``--no-user-config-files`` options.

``--no-system-config-files``
  Skip all system-wide configuration files, both cockpit and depot.

``--no-user-config-files``
  Skip the user configuration file, both cockpit and depot.

``--depot-file DEPOT-CONFIG-PATH``
  Filepath for the depot device configuration.  This option can be
  specified multiple times.  If depot files are defined via command
  line, no other depot files will be read, not even those mentioned on
  config files.

``--debug``
  Set the logging level to debug.

.. _cockpit_config_precedence:

Precedence of option values
---------------------------

Cockpit can be configured via multiple config files and command line
options, so the same option may be defined in multiple places.  The
precedence order in such case is:

1. command line option
2. config file set via command line
3. user config file
4. system-wide config files
5. cockpit fallback values

This enables users to have a configuration file that overrides
system-wide settings, or to use command line options for one-off
change of settings.

GUI Configuration
=====================

Cockpit also generates a config.py file which caches GUI related information like the layout of windows,
and which windows are open, for when it is next opened. It may be useful to directly edit the values here,
if, for instance, the PyShell window is not visible on startup, but many of the values here are
editable indirectly by e.g. arranging the windows with the mouse.

.. The userConfig stuff is not documented.  Not sure if it should be
   documented at all, seems more like cache.  Parts of it that makes
   sense to configure can have system-wide value, in which case should
   be moved into cockpit config.
