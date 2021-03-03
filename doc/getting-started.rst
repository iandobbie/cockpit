.. Copyright (C) 2021 Martin Hailstone
   This work is licensed under the Creative Commons
   Attribution-ShareAlike 4.0 International License.  To view a copy of
   this license, visit http://creativecommons.org/licenses/by-sa/4.0/.

Getting Started
***************

Cockpit will run by default with a set of dummy devices. Configuring Cockpit to use your own devices requires two things:

- First, you need a Python-Microscope `device-server <https://www.micron.ox.ac.uk/software/microscope/doc/architecture/device-server.html>`_. If you have a config.py file for Python-Microscope, you can run this with ``device-server PATH-TO-CONFIGURATION-FILE``.

- Next, you need to `configure Cockpit <doc\config.rst>`_ to use these devices. This is achieved through a Depot file placed at a particular location.
