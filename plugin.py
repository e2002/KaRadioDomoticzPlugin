# KaRadio
#
# v0.1.4
#
# KaRadio plugin for Domoticz Home Automation System
# https://github.com/e2002/KaRadioDomoticzPlugin
#
# pss, bro, want some online right now?
#
"""
<plugin key="KaRadio" name="KaRadio" author="easy [support@k210.org]" version="0.1.3">
    <params>
        <param field="Mode1" label="KaRadio IP Address" width="200px" required="true" default=""/>
        <param field="Mode2" label="Interval (sec)" width="30px" required="true" default="2"/>
        <param field="Mode6" label="Debug" width="150px">
            <options>
                <option label="Verbose" value="Verbose"/>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal" default="true" />
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import json
import socket
import re
import threading
import time

class BasePlugin:
    def __init__(self):
        self.UNIT_PLAYLIST       = 1
        self.UNIT_PLAYPAYSE      = 2
        self.UNIT_PREV           = 3
        self.UNIT_NEXT           = 4
        self.UNIT_TITLE          = 5
        self.UNIT_VOLDN          = 6
        self.UNIT_VOLTX          = 7
        self.UNIT_VOLUP          = 8
        self.UNIT_VOLLVL         = 9
        self.lastPlaylist        = None
        self.lastPlayPause       = None
        self.lastTitle           = None
        self.lastVolume          = None
        
        #self.startupScenes       = "Stop|Refresh"
        self.startupScenes       = "Стоп|Обновить"
        
        self.Online = True
        self.hb = 0

        self.messageThread = threading.Thread(name="KaStatusThread", target=BasePlugin.handleMessage, args=(self,))
        
        return
        
    def onStart(self):
        try:
            self.kaIP                = Parameters["Mode1"]
            self.delay               = int(Parameters["Mode2"])
            self.debugging           = Parameters["Mode6"]
            
            if self.debugging == "Verbose":
                Domoticz.Debugging(-1)
                DumpConfigToLog()
            if self.debugging == "Debug":
                Domoticz.Debugging(62)
                DumpConfigToLog()
            
            if not self.UNIT_PLAYLIST in Devices:
                Options = {"Scenes": self.startupScenes, "LevelNames": "|", "LevelOffHidden": "false", "SelectorStyle": "1"}
                Domoticz.Device(Name="Playlist", Unit=self.UNIT_PLAYLIST, Type=244, Subtype=62 , Switchtype=18, Used=0, Options = Options, Image=12).Create()
            if not self.UNIT_PLAYPAYSE in Devices:
                Domoticz.Device(Name="Play/Pause", Unit=self.UNIT_PLAYPAYSE, Type=244, Subtype=73 , Switchtype=0, Used=0, Image=9).Create()
            if not self.UNIT_PREV in Devices:
                Domoticz.Device(Name="Prev", Unit=self.UNIT_PREV, Type=244, Subtype=73 , Switchtype=9, Used=0, Image=0).Create()
            if not self.UNIT_NEXT in Devices:
                Domoticz.Device(Name="Next", Unit=self.UNIT_NEXT, Type=244, Subtype=73 , Switchtype=9, Used=0, Image=0).Create()
            if not self.UNIT_TITLE in Devices:
                Domoticz.Device(Name="Title", Unit=self.UNIT_TITLE, Type=243, Subtype=19, Used=0, Image=0).Create()
            if not self.UNIT_VOLDN in Devices:
                Domoticz.Device(Name="Vol Down", Unit=self.UNIT_VOLDN, Type=244, Subtype=73, Switchtype=9, Used=0, Image=8).Create()
            if not self.UNIT_VOLTX in Devices:
                Domoticz.Device(Name="Vol Level", Unit=self.UNIT_VOLTX, Type=243, Subtype=19, Used=0, Image=8).Create()
            if not self.UNIT_VOLUP in Devices:
                Domoticz.Device(Name="Vol UP", Unit=self.UNIT_VOLUP, Type=244, Subtype=73, Switchtype=9, Used=0, Image=8).Create()
            if not self.UNIT_VOLLVL in Devices:
                Domoticz.Device(Name="Volume", Unit=self.UNIT_VOLLVL, Type=244, Subtype=73, Switchtype=7, Used=0, Image=8).Create()

            self.UpdatePlaylist()
            self.messageThread.start()
            
        except Exception as e:
            Domoticz.Error("Exception in onStart, called with detail: '"+str(e)+"'")
    
    def kaopen(self, url):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)                 
            s.settimeout(2)
            s.connect((self.kaIP, 80))
            s.sendall(("GET /?"+url+" HTTP/1.1\r\n\r\n").encode())
            response = s.recv(2048)
            s.close()
            return response.decode("utf-8", "ignore")
        except Exception as e:
            return False
        finally:
            s.close()
    
    def stepVol(self, vstep):
        html = self.kaopen('infos')
        if html==False: return
        result = re.findall(r'^vol:\s(.+?)$', html, re.MULTILINE)
        if result:
            vol = int(result[0]) * 200 / 254
            vol = int(round(vol, -1)/2)
            if vstep=="vdn":
                vol -= 5
                if vol < 0: vol=0
            else:
                vol += 5
                if vol > 100: vol=100
            vol = vol * 254 / 100
            self.kaopen('volume='+str(vol))

    def UpdatePlaylist(self):
        levelnames = self.startupScenes
        item = 0
        while item < 254:
            html = self.kaopen('list='+str(item))
            if html==False: break
            result = re.findall(r"\r\n\r\n(.+?)$", html)
            if len(result)<1: break;
            levelnames += "|"+result[0]
            item += 1;
        scenes = '|'*levelnames.count('|')
        Options = Devices[self.UNIT_PLAYLIST].Options
        Options["Scenes"]=scenes
        Options["LevelNames"]=levelnames
        Domoticz.Debug("UpdatePlaylist Options: '"+str(Options)+"'")
        nValue = 0 if Devices[self.UNIT_PLAYLIST].LastLevel==0 else 1
        Devices[self.UNIT_PLAYLIST].Update(nValue=nValue,sValue=str(Devices[self.UNIT_PLAYLIST].LastLevel),Options = Options, TimedOut = False)

    def handleMessage(self):
        try:
            Domoticz.Debug("Entering message handler")
            while self.Online:
                if self.hb==0:
                    response = self.kaopen('infos')
                    if response:
                        result = re.findall(r"vol:\s(.+?)\nnum:\s(.+?)\nstn:\s(.+?)\ntit:\s(.+?)\nsts:\s(.+?)", str(response), re.MULTILINE)
                        if result:
                            volume = int(round(int(result[0][0])*200/254,-1)/2)
                            stanum = int(result[0][1])
                            station= result[0][2]
                            title  = result[0][3]
                            status = int(result[0][4])
                            playing = "" if status==1 else "[STOPPED]"
                            current = (station+": " + title + playing).upper()
                            if volume!=self.lastVolume:
                                Devices[self.UNIT_VOLTX].Update(nValue=0,sValue=str(volume)+"%", TimedOut = False)
                                Devices[self.UNIT_VOLLVL].Update(nValue=1,sValue=str(volume), TimedOut = False)
                                self.lastVolume = volume
                            if status!=self.lastPlayPause:
                                if status==1:
                                    Devices[self.UNIT_PLAYPAYSE].Update(nValue=1,sValue="On", TimedOut = False)
                                    sValue = str((stanum+2)*10) if status==1 else "0"
                                    Devices[self.UNIT_PLAYLIST].Update(nValue=1,sValue=sValue, TimedOut = False)
                                else:
                                    Devices[self.UNIT_PLAYPAYSE].Update(nValue=0,sValue="Off", TimedOut = False)
                                    Devices[self.UNIT_PLAYLIST].Update(nValue=0,sValue="0", TimedOut = False)
                                self.lastPlayPause=status
                            if stanum!=self.lastPlaylist:
                                nValue = 1 if status==1 else 0
                                sValue = str((stanum+2)*10) if status==1 else "0"
                                Devices[self.UNIT_PLAYLIST].Update(nValue=nValue,sValue=sValue, TimedOut = False)
                                self.lastPlaylist=stanum
                            if current!=self.lastTitle:
                                Domoticz.Debug("handleMessage current: '"+current+"'")
                                Devices[self.UNIT_TITLE].Update(nValue=0,sValue=current, TimedOut = False)
                                self.lastTitle=current
                self.hb += 1
                if self.hb >= self.delay: self.hb=0
                time.sleep(1)
                
        except Exception as err:
            Domoticz.Error("Exception in handleMessage, called with detail: "+str(err))

    def onCommand(self, Unit, Command, Level, Color):
        try:
            if Unit==self.UNIT_PLAYLIST:
                nValue = 0 if Level==0 else 1
                Devices[Unit].Update(nValue=nValue, sValue=str(Level), TimedOut = False)
                if Level==0:
                    self.kaopen("stop")
                elif Level==10:
                    self.UpdatePlaylist()
                else:
                    station = Level / 10 - 2
                    self.kaopen("play="+str(station))
            if Unit==self.UNIT_PLAYPAYSE:
                playcommand = 'stop' if Command=="Off" else 'start'
                nValue = 0 if Command=="Off" else 1
                self.kaopen(playcommand)
                Devices[Unit].Update(nValue=nValue, sValue=Command, TimedOut = False)
                
            if Unit==self.UNIT_PREV:
                self.kaopen("prev")
            if Unit==self.UNIT_NEXT:
                self.kaopen("next")
            if Unit==self.UNIT_VOLDN:
                self.stepVol("vdn")
            if Unit==self.UNIT_VOLUP:
                self.stepVol("vup")
            if Unit==self.UNIT_VOLLVL:
                vol = int(Level)*254/100
                self.kaopen('volume='+str(vol))
            Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level)+ ", Color: "+str(Color))
            
        except Exception as err:
            Domoticz.Error("Exception in onCommand, called with detail: "+str(err))
            
    def onStop(self):
        Domoticz.Log("Thread Stopping...")
        self.Online = False

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()
          
def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)
       
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return
