# Quick solution to control the settings of the WebCams through the
# v412-ctl package available on Linux.
#
# Author: Christian Dorfer (dorfer@phys.ethz.ch)

"""
Requirements:
    - pip install sh
    - pip install pyqt5 (needs Qt5 backend on system)
    - v4l-utils: Use your package manger of choice (e.g. apt-get install v4l-utils)

Usage:
    python main.py

"""

import argparse
import json
import os
import re
import sh
import sys
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout, QSlider
from PyQt5.Qt import Qt, QLabel, QGridLayout, QPushButton, QFileDialog


class CameraControl(object):
    """
    Interface class to the v4l2-ctl package.
    """

    RE_CTL = re.compile(r"(\w+).*?\(([a-z]+)\)\s*:\s(.*)$")
    ATTRS = (
        "min",
        "max",
        "step",
        "default",
        "value",
        "flags",
    )

    def get_ctls(self):
        self.ctrls = {}
        if self.device:
            ret = self.cmd("-d", self.device, "-l")
        else:
            ret = self.cmd("-l")
        for line in ret:
            m = self.RE_CTL.split(line)
            if not m:
                continue
            name = m[1]
            ctl = {}
            ctl["type"] = m[2]
            rest = m[3]
            for attr, re_attr in self.re_attrs:
                m = re_attr.search(rest)
                if not m:
                    continue
                val = m[1]
                try:
                    val = int(val)
                except ValueError:
                    pass
                ctl[attr] = val
            self.ctrls[name] = ctl

    def __init__(self, device):
        self.device = device
        self.cmd = sh.Command("/usr/bin/v4l2-ctl")
        self.re_attrs = [(a, re.compile(a + r"=(-?\w+)")) for a in self.ATTRS]
        self.get_ctls()

    def getValue(self, name):
        try:
            if self.device:
                ret = self.cmd("-d", self.device, "--get-ctrl", name)
            else:
                ret = self.cmd("--get-ctrl", name)
            val = [int(s) for s in ret.split() if s.isdigit()]
            self.ctrls[name]["value"] = val[0]
            return val[0]
        except:
            print('Ups, could not read value.')
            return 0

    def setValue(self, name, val):
        if self.ctrls[name].get("flags", "") == "inactive":
            return True
        try:
            if self.device:
                self.cmd("-d", self.device, "--set-ctrl", (name+"="+str(val)))
            else:
                self.cmd("--set-ctrl", (name+"="+str(val)))
        except:
            print('Ups, could not set value for ', name, '.')
            return False
        self.ctrls[name]["value"] = val
        return True

    def update(self, reset=False):
        # bool/menu needs to be done first because they might change
        # the availability of parameters.
        for name, c in self.ctrls.items():
            if c["type"] == "int":
                continue
            if reset:
                val = c["default"]
            else:
                val = c["value"]
            self.setValue(name, val)
        for name, c in self.ctrls.items():
            if c["type"] == "bool" or c["type"] == "menu":
                continue
            if reset:
                val = c["default"]
            else:
                val = c["value"]
            self.setValue(name, val)


class Window(QWidget):

    def __init__(self, cc):
        super().__init__()

        self.camCtr = cc
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Camera Control')
        self.setMinimumWidth(260)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(2)

        self.lbls = {}
        self.sls = {}
        self.buttons = {}
        self.button_status = {}
        row = 1
        for name, c in self.camCtr.ctrls.items():
            txt = name.replace("_", " ").capitalize() + ":"
            txt = txt.replace("White balance temperature", "WB temperature")
            lbl = QLabel(txt)
            self.grid.addWidget(lbl, row, 1, 1, 1, Qt.AlignRight)
            self.lbls[name] = lbl
            if c["type"] == "bool":
                button = QPushButton()
                if c["value"]:
                    button.setText('ON')
                    button.setStyleSheet("background-color: green")
                    self.button_status[name] = True
                else:
                    button.setText('OFF')
                    button.setStyleSheet("background-color: red")
                    self.button_status[name] = False
                button.clicked.connect(
                    lambda val, name=name: self.button_Change(val, name))
                self.grid.addWidget(
                    button, row, 2, 1, 1, Qt.AlignCenter)
                self.buttons[name] = button
            else:
                sl = QSlider()
                sl.setOrientation(Qt.Horizontal)
                sl.setMaximum(c["max"])
                sl.setMinimum(c["min"])
                sl.valueChanged.connect(
                    lambda val, name=name: self.sl_Change(val, name))
                sl.setMinimumWidth(250)
                sl.setTickInterval(c.get("step", 1))
                sl.setValue(c["value"])
                if c.get("flags", "") == "inactive":
                    lbl.setDisabled(True)
                    sl.setDisabled(True)
                self.grid.addWidget(sl, row, 2, 1, 1, Qt.AlignRight)
                self.sls[name] = sl
            row += 1

        self.actions_grid = QGridLayout()
        self.actions = {}
        for i, action in enumerate(
                ("default", "sync", "update", "load", "save")):
            b = QPushButton()
            b.setText(action.capitalize())
            b.clicked.connect(
                lambda _, action=action: self.action_Slot(action))
            self.actions_grid.addWidget(b, 1, i, 1, 1, Qt.AlignCenter)
        self.grid.addLayout(self.actions_grid, row, 1, 1, 2, Qt.AlignCenter)

        self.mainLayout = QHBoxLayout()
        self.mainLayout.addLayout(self.grid)
        self.setLayout(self.mainLayout)
        self.show()

    def sl_Change(self, val, name):
        if not self.camCtr.setValue(name, val):
            # Give user feedback if parameter was not
            # accepted. Unfortunately, not all invalid parameters are
            # actually flagged.
            self.sync()
            return

    def sync(self):
        self.camCtr.get_ctls()
        for name, c in self.camCtr.ctrls.items():
            if c["type"] == "bool":
                if c["value"]:
                    self.buttons[name].setText('ON')
                    self.buttons[name].setStyleSheet("background-color: green")
                    self.button_status[name] = True
                else:
                    self.buttons[name].setText('OFF')
                    self.buttons[name].setStyleSheet("background-color: red")
                    self.button_status[name] = False
            else:
                self.sls[name].setValue(c["value"])
                if c.get("flags", "") == "inactive":
                    self.sls[name].setDisabled(True)
                    self.lbls[name].setDisabled(True)
                else:
                    self.sls[name].setDisabled(False)
                    self.lbls[name].setDisabled(False)

    def button_Change(self, _, name):
        if self.button_status[name]:
            self.buttons[name].setText('OFF')
            self.buttons[name].setStyleSheet("background-color: red")
            self.button_status[name] = False
            self.camCtr.setValue(name, "0")
        else:
            self.buttons[name].setText('ON')
            self.buttons[name].setStyleSheet("background-color: green")
            self.button_status[name] = True
            self.camCtr.setValue(name, "1")
        # Check if any controls have become enabled.
        self.sync()

    def action_Slot(self, name):
        if name == "default":
            self.camCtr.update(reset=True)
        elif name == "update":
            self.camCtr.update()
        elif name == "save" or name == "load":
            conf_dir = os.path.join(Path.home(), ".config", "cam_control")
            Path(conf_dir).mkdir(parents=True, exist_ok=True)
            if name == "save":
                file_name, _ = QFileDialog.getSaveFileName(
                    self, "Save Cam Control configuration", conf_dir,
                    "Cam Control Conf (*.ccconf)")
                if file_name:
                    if not file_name.endswith(".ccconf"):
                        file_name += ".ccconf"
                    with open(file_name, "w") as fd:
                        json.dump(self.camCtr.ctrls, fd)
            else:
                file_name, _ = QFileDialog.getOpenFileName(
                    self, "Load Cam Control configuration", conf_dir,
                    "Cam Control Conf (*.ccconf)")
                if file_name:
                    with open(file_name, "r") as fd:
                        self.camCtr.ctrls = json.load(fd)
                    self.camCtr.update()
        self.sync()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Handle Camera Controls via v4l2-ctl.')
    parser.add_argument(
        '--device', '-d', type=str, default ='',
        help='v4l2 to use, use "v4l2-ctl --list-devices" to list all of them')
    args = parser.parse_args()
    camCtr = CameraControl(args.device)
    app = QApplication(sys.argv)
    window = Window(camCtr)
    sys.exit(app.exec_())
