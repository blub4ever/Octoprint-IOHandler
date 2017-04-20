# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.events import eventManager, Events
from flask import jsonify, make_response
import RPi.GPIO as GPIO

# sudo service octoprint restart
#python setup.py develop
#python -t octoprint_iohandler/__init__.py
#source ~/oprint/bin/activate

class IOHandlerPlugin(octoprint.plugin.StartupPlugin,
                             octoprint.plugin.ShutdownPlugin,
                             octoprint.plugin.EventHandlerPlugin,
                             octoprint.plugin.TemplatePlugin,
                             octoprint.plugin.SettingsPlugin):


    def initialize(self):
        self._logger.info("Running RPi.GPIO version '{0}'".format(GPIO.VERSION))
        if GPIO.VERSION < "0.6":       # Need at least 0.6 for edge detection
            raise Exception("RPi.GPIO must be greater than 0.6")
        GPIO.setmode(GPIO.BOARD)       # Use the board numbering scheme
        GPIO.setwarnings(True)        # Disable GPIO warnings

    def on_after_startup(self):
        self._logger.info("IOHandler started - Running RPi.GPIO version '{0}'".format(GPIO.VERSION))

        self.relais4 = int(self._settings.get(["relais4"]))

        self.ledReady = int(self._settings.get(["ledReady"]))
        self.ledReadyToPrint = int(self._settings.get(["ledReadyToPrint"]))
        self.ledPrinting = int(self._settings.get(["ledPrinting"]))
        self.led7 = int(self._settings.get(["led7"]))

        self.bounce = int(self._settings.get(["bounce"]))
        self.switch = int(self._settings.get(["switch"]))

        self.switches = {}
        self.relais = {}


        # relais light
        if self._settings.get(["relaisLight"]) != -1:
            self.relais["light"] = RelaisHolder(self, self._settings.get(["relaisLight"]), "Light Relais", False)

        #realis heatbed
        if self._settings.get(["relaisHeatbed"]) != -1:
            self.relais["heatbead"] = RelaisHolder(self, self._settings.get(["relaisHeatbed"]), "Heatbed", False)

        #relais power
        if self._settings.get(["relaisPower"]) != -1:
            self.relais["power"] = RelaisHolder(self, self._settings.get(["relaisPower"]), "Power", False)

        if self._settings.get(["relais4"]) != -1:
            self.relais["relais4"] = RelaisHolder(self, self._settings.get(["relais4"]), "Relais4", False)


        # switch for light
        if self._settings.get(["switchLight"]) != -1:
            if self.relais.get("light") != None:
                self.switches["light"] = LEDSwitch(self,"Light",self._settings.get(["switchLight"]),False, int(self._settings.get(["ledLight"])),False,[self.relais['light']],False)
            else:
                self.switches["light"] = LEDSwitch(self, "Light", self._settings.get(["switchLight"]), False,
                                                   int(self._settings.get(["ledLight"])), False, [], False)
        # pause switch
        if self._settings.get(["switchPause"]) != -1:
            self.switches["pause"] = PauseSwitch(self,"Pause",self._settings.get(["switchPause"]),False,int(self._settings.get(["ledPause"])),False)

        # standby switch
        if self._settings.get(["switchStandby"]) != -1:
            relaisArray = []

            if self.relais.get("heatbead") != None:
                relaisArray.append(self.relais["heatbead"])

            if self.relais.get("power") != None:
                relaisArray.append(self.relais["power"])

            self.switches["standby"] = StandbySwitch(self,"Standby",self._settings.get(["switchStandby"]),False,int(self._settings.get(["ledStandby"])),False,relaisArray,True)

        # filament senosr
        if self._settings.get(["filamentSensor"]) != -1:
            self.switches["filamentSensor"] = FilamentSensor(self,"Filament Sensor",self._settings.get(["filamentSensor"]),False)


        if self._settings.get(["ledReady"]) != -1:   # If a pin is defined
            self._logger.info("LED Ready  active on GPIO Pin [%s]"%self.ledReady)
            GPIO.setup(self.ledReady, GPIO.OUT, initial=GPIO.HIGH)    # Initialize GPIO as INPUT

        if self._settings.get(["ledReadyToPrint"]) != -1:   # If a pin is defined
            self._logger.info("LED readyToPrint  active on GPIO Pin [%s]"%self.ledReadyToPrint)
            GPIO.setup(self.ledReadyToPrint, GPIO.OUT, initial=GPIO.LOW)    # Initialize GPIO as INPUT

        if self._settings.get(["ledPrinting"]) != -1:   # If a pin is defined
            self._logger.info("LED Printing  active on GPIO Pin [%s]"%self.ledPrinting)
            GPIO.setup(self.ledPrinting, GPIO.OUT, initial=GPIO.LOW)    # Initialize GPIO as INPUT

        if self._settings.get(["led7"]) != -1:   # If a pin is defined
            self._logger.info("LED 7  active on GPIO Pin [%s]"%self.led7)
            GPIO.setup(self.led7, GPIO.OUT, initial=GPIO.LOW)    # Initialize GPIO as INPUT

    def on_shutdown(self):
        self._logger.info("Cleaning gpio up")
        GPIO.cleanup()

    def get_settings_defaults(self):
        return dict(
            switchLight = 37,
	        ledLight = 33,
            relaisLight=22,

			switchPause = 35,
            ledPause=31,

            switchStandby = 29,
            ledStandby = 15,

            relaisHeatbed=18,
            relaisPower=16,

            ledReady = 40, #ready
            ledReadyToPrint = 38, #ready to print
            ledPrinting = 36, # print in progress
            led7 = 32, #hot

            filamentSensor = 7,

            relais4=12,

            emergencystop = -1,
            bounce  = 500,  # Debounce 250ms
            switch  = 0    # Normally Open
        )

    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=False)]

    def on_event(self, event, payload):
        if event == Events.PRINT_STARTED:
            self._logger.info("Print started")
            GPIO.output(self.ledPrinting, GPIO.HIGH)
            # switching off pause mode, in case it was activated
            if self.switches.get("pause") != None:
                self.switches["pause"].toogleState(False)
            #adding filament Sensor
            if self.switches.get("filamentSensor") != None:
                self.switches["filamentSensor"].addEvent()
        elif (event == Events.PRINT_FAILED) or (event == Events.PRINT_DONE) or (event == Events.PRINT_CANCELLED):
            self._logger.info("Print stopped")
            GPIO.output(self.ledPrinting, GPIO.LOW)
            GPIO.output(self.ledReadyToPrint, GPIO.HIGH)
            # adding filament Sensor
            if self.switches.get("filamentSensor") != None:
                self.switches["filamentSensor"].removeEvent()
        elif event == Events.PRINT_PAUSED:
            self._logger.info("Pause Event")
            if self.switches.get("pause") != None:
                self.switches["pause"].toogleState(True)
        elif event == Events.ERROR:
            self._logger.info("Error Event")

    def get_update_information(self):
        return dict(
            octoprint_filament=dict(
                displayName="IOHandler",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="blub4ever",
                repo="Octoprint-Filament-Reloaded",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/kontakt/Octoprint-Filament-Reloaded/archive/{target_version}.zip"
            )
        )

class RelaisHolder:

    #GPIO.LOW
    def __init__(self, parent, pin, name, state):
        self.parent = parent
        self.name = name
        self.pin = pin
        self.state = state

        self.parent._logger.info("Relais \"%s:\"  active on GPIO Pin [%s]" %(name,pin))
        GPIO.setup(pin, GPIO.OUT, initial= GPIO.HIGH if state else GPIO.LOW)

    def toogle(self):
        self.state = not self.state
        self.parent._logger.info("Relais \"%s:%s\" toggelt to %s" % (self.name, self.pin, "active" if self.state else "inactive"))
        GPIO.output(self.pin, (GPIO.HIGH if self.state else GPIO.LOW))

    def turnOn(self):
        self.state = True
        self.parent._logger.info("Relais \"%s:%s\" toggelt to active" % (self.name, self.pin))
        GPIO.output(self.pin, GPIO.HIGH)

    def turnOff(self):
        self.state = False
        self.parent._logger.info("Relais \"%s:%s\" toggelt to inactive" % (self.name, self.pin))
        GPIO.output(self.pin, GPIO.LOW)


class SwitchLEDHodler:
    def __init__(self, parent, buttonName, buttonPin, inverted, buttonFunction, ledPin, isActive, relaisToToggle, relaisInverted, addEvent):
        self.parent = parent
        self.buttonName = buttonName
        self.buttonPin = buttonPin
        self.buttonFunction = buttonFunction
        self.ledPin = ledPin
        self.isActive = isActive
        self.relaisToToggle = relaisToToggle
        self.relaisInverted = relaisInverted
        self.inverted = inverted

        # setting gpio and event
        self.parent._logger.info("Button \"%s\" active on GPIO Pin [%s]" %(buttonName,buttonPin))

        GPIO.setup(buttonPin, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)
        if addEvent:
            self.addEvent()

        # init light pin if provieded
        if ledPin != -1:   # If a pin is defined
            self.parent._logger.info("Button \"%s:%s\" has a led, active on GPIO Pin [%s]"%(buttonName,buttonPin,ledPin))
            GPIO.setup(ledPin, GPIO.OUT, initial=GPIO.LOW)

    def addEvent(self):
        self.parent._logger.info("Added click event for Button \"%s:%s\" on %s" %(self.buttonName,self.buttonPin,("rising" if not self.inverted else "falling")))
        GPIO.add_event_detect(self.buttonPin, GPIO.RISING if not self.inverted else GPIO.FALLING, callback=self.check_gpio, bouncetime=self.parent.bounce)

    def removeEvent(self):
        self.parent._logger.info("Removed event for Button \"%s:%s\"" %(self.buttonName,self.buttonPin))
        GPIO.remove_event_detect(self.buttonPin)

    def toogleState(self, force=None):
        if self.ledPin != -1:
            if force == None:
                if self.isActive:
                    GPIO.output(self.ledPin, GPIO.LOW)
                    self.parent._logger.info("Toggling LED %s to low" % (self.ledPin))
                else:
                    GPIO.output(self.ledPin, GPIO.HIGH)
                    self.parent._logger.info("Toggling LED %s to high" % (self.ledPin))
                self.isActive = not self.isActive
            else:
                self.parent._logger.info("Force state to %s" %("active" if force else "inactive" ))
                GPIO.output(self.ledPin, GPIO.HIGH if force else  GPIO.LOW)
                self.isActive = True if force else False

    def toogleRelais(self):
        if self.relaisToToggle:
            for tRelais in self.relaisToToggle:
                if self.isActive:
                    if self.relaisInverted:
                        self.parent._logger.info("Relais inverted for Button \"%s:%s\"" % (self.buttonName, self.buttonPin))
                        tRelais.turnOff()
                    else:
                        tRelais.turnOn()
                else:
                    if self.relaisInverted:
                        self.parent._logger.info("Relais inverted for Button \"%s:%s\"" % (self.buttonName, self.buttonPin))
                        tRelais.turnOn()
                    else:
                        tRelais.turnOff()
        else:
            self.parent._logger.info("No relais to toggle for Button \"%s:%s\"" %(self.buttonName,self.buttonPin))

    def check_gpio(self, channel):
        state = GPIO.input(self.buttonPin)

        self.parent._logger.info("Button \"%s:%s\" state [%s]"%(self.buttonName,self.buttonPin, state))

        self.toogleState()
        self.toogleRelais()
        self.buttonFunction()

class LEDSwitch(SwitchLEDHodler):
    def __init__(self, parent, buttonName, buttonPin, inverted, ledPin, isActive, relaisToToggle, relaisInverted):
        SwitchLEDHodler.__init__(self, parent, buttonName,  buttonPin, inverted,self.buttonClicked, ledPin, isActive, relaisToToggle, relaisInverted, True)

    def buttonClicked(self):
        self.parent._logger.info("Button \"%s:%s\" custom routine, do nothing"%(self.buttonName,self.buttonPin))

class PauseSwitch(SwitchLEDHodler):
    def __init__(self, parent, buttonName, buttonPin, inverted, ledPin, isActive):
        SwitchLEDHodler.__init__(self, parent, buttonName, buttonPin, inverted, self.buttonClicked, ledPin, isActive, [], False, True)

    def toogleState(self, force=None):
        if self.parent._printer.is_printing() or force != None:
            SwitchLEDHodler.toogleState(self,force)
        else:
            self.parent._logger.info("Button \"%s:%s\" do not change state, not printing" % (self.buttonName, self.buttonPin))

    def buttonClicked(self):
        self.parent._logger.info("Button \"%s:%s\" custom routine, do nothing" % (self.buttonName, self.buttonPin))

        if self.parent._printer.is_printing():
            self.parent._logger.info("Button \"%s:%s\" halting print" % (self.buttonName, self.buttonPin))
            self.parent._printer.toggle_pause_print()


class StandbySwitch(SwitchLEDHodler):
    def __init__(self, parent, buttonName, buttonPin, inverted, ledPin, isActive, relaisToToggle, relaisInverted):
        SwitchLEDHodler.__init__(self, parent, buttonName, buttonPin, inverted, self.buttonClicked, ledPin, isActive, relaisToToggle, relaisInverted, True)

    def buttonClicked(self):
        self.parent._logger.info("Standby Button cicked")


class FilamentSensor(SwitchLEDHodler):
    def __init__(self, parent, buttonName, buttonPin, inverted):
        SwitchLEDHodler.__init__(self, parent, buttonName, buttonPin, inverted, self.buttonClicked, -1, False, None, False, False)

    def buttonClicked(self):
        self.parent._logger.info("Button \"%s:%s\" custom routine, do nothing" % (self.buttonName, self.buttonPin))

        if self.parent._printer.is_printing():
            self.parent._logger.info("Button \"%s:%s\" halting print" % (self.buttonName, self.buttonPin))
            self.parent._printer.toggle_pause_print()

__plugin_name__ = "IOHandler"
__plugin_version__ = "0.1.0"



def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = IOHandlerPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
}