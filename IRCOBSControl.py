#! /usr/bin/env python
try:
    import OBS
except:
    pass
import sys

#need irc from pip
import irc.client
import irc.logging

from threading import Thread
from Keys import oauth #Key.py with oauth="oauth:twitchkeyhere"
import queue 

import time

class MyIRC(Thread):
    isRunning = True
    debug = True
    client = 0
    connection = 0
    isConnected = False
    command =  0
    ratelimit = 3 #seconds
    spacestring = ""
    def __init__(self,qSend,qRecv,server,port,username,password,targetChannel):
        super(MyIRC, self).__init__()
        self.servername = server
        self.username = username
        self.password = password
        self.port = port
        self.target = targetChannel
        self.qSend = qSend
        self.qRecv = qRecv
        self.op_list = {'andyroid'} #op status is not instant
        self.lastSent = time.time()

    def connect(self):
        print ("Connecting")
        self.client = irc.client.Reactor()
        try:
            self.isConnected = True
            self.server = self.client.server()
            self.connection = self.server.connect(self.servername, self.port, self.username,self.password)
        except :
            print ("Could not connect")
            print (sys.exc_info()[1])
            return

        #add all handlers
        self.connection.add_global_handler("welcome", self.on_connect)
        self.connection.add_global_handler("disconnect", self.on_disconnect)
        self.connection.add_global_handler("pubmsg",self.on_pubmsg)
        self.connection.add_global_handler("privnotice",self.on_privnotice)
        self.connection.add_global_handler("unknowncommand",self.on_unknowncommand)
        self.connection.add_global_handler("error",self.on_unknowncommand)
        self.connection.add_global_handler("mode",self.on_mode)

    def on_mode(self,connection, event):
        #add to list of opers
        self.op_list.add(event.arguments[1])
        if self.debug:
            print (event.arguments[1])

    def on_unknowncommand(self,connection, event):
        print ("Error")
        print (event.arguments)

    def on_privmsg(self,connection, event):
        self.print_event(event)
        pass


    def disconnect(self):
        if(self.isConnected):
            self.client.disconnect_all()
            self.server.close()
            self.isConnected = False
        pass

    def on_disconnect(self,connection, event):
        print (event.arguments)
        self.isConnected = False
        #set gui stuff
        pass

    def on_privnotice(self,connection,event):
        print("privnotice")
        self.print_event(event)
        if event.arguments[0] == "Login unsuccessful":
            self.disconnect()
            print("Login unsuccessful")

    def print_event(self,event):
        if not self.debug:
            return
        
        print("#######")
        try:
            print(event.type)
            print(event.arguments)
            print(event.target)
            print(event.source)
        except:
            pass
        print("#######")

    def on_connect(self,connection, event):
        print (event.arguments)

        connection.send_raw("CAP REQ :twitch.tv/membership")
        if irc.client.is_channel(self.target):
            connection.join(self.target)
            print("Connected")
        else:
            connection.join(self.target)
            print("Bad Channel")
            return

    #This is the main message function
    def on_pubmsg(self,connection, event):
        username = event.source.split("!")[0]
        self.print_event(event)

        if username in self.op_list:
            if event.arguments[0].split()[0].lower() == "!obs":
                self.qRecv.put(event.arguments[0])

    def processIRC(self):
        if(self.isConnected):
            self.client.process_once()
            #process messages to send
            if not self.qSend.empty() and time.time() > self.lastSent:
                text = self.qSend.get()
                if text == "quit":
                    self.isRunning = False
                    return
                self.connection.privmsg(self.target,text)
                self.lastSent = time.time() + self.ratelimit
            elif not self.qSend.empty():
                #dump messages but check for quit
                while not self.qSend.empty():
                    text = self.qSend.get()
                    if text == "quit":
                        self.isRunning = False
                        return
            else:
                return



    def run(self):
        self.connect() #connect to the server
        while self.isRunning:
            self.processIRC()
            time.sleep(0.01)

        self.disconnect()


class IRCOBSControl(OBS.ImageSource):
    def __init__(self,config):
        self.config = config

        servername = "irc.twitch.tv"
        password = oauth
        username = "streamerschair"
        port = 6667
        target = "#andyroid"

        self.commandCooldown = 15
        self.lastCommand = time.time()

        self.qSend = queue.Queue()
        self.qRecv = queue.Queue()

        self.myirc = MyIRC(self.qSend,self.qRecv,servername,port,username,password,target)
        self.myirc.start()

        self.commandToFunc = {"gamma": self.setSourceGamma,
                              "scene": self.changeScene,
                              "hide": self.sceneItemVisableHide,
                              "show": self.sceneItemVisableShow,
                              "list": self.listItems}


    def EndScene(self):
        OBS.Log(u"endScene")

    def Render(self,pos,size):
        pass

    def Destructor(self):
        self.qSend.put("quit")
        self.myirc.join()
        pass

    def GlobalSourceLeaveScene(self):
        pass

    def GlobalSourceEnterScene(self):
        pass

    def sceneItemVisableHide(self,command):
        self.sceneItemVisable(command,False)
        pass

    def sceneItemVisableShow(self,command):
        self.sceneItemVisable(command,True)
        pass

    def sceneItemVisable(self,command,value):
        sourceName = " ".join(command)
        sceneItem = OBS.GetScene().GetSceneItemByName(sourceName)
        if not sceneItem:
            return
        sceneItem.SetRender(value)       

        
    def listItems(self,command):
        value = command[0]
        
        if value == "scenes":
            sceneListElement = OBS.GetSceneListElement()
            print(sceneListElement.GetName())
            sceneList = []
            for i in range(0,sceneListElement.NumElements()):
                sceneList.append(sceneListElement.GetElementByID(i).GetName())
            self.qSend.put("Available scenes: " +str(sceneList))
            pass
        elif value == "sources":
            scene = OBS.GetScene()
            sourceList = []
            for i in range(0,scene.NumSceneItems()):
                sourceList.append(scene.GetSceneItemByID(i).GetName())
            self.qSend.put("Available sources: " +str(sourceList))
        else:
            return

    def changeScene(self,command):
        sceneName = " ".join(command)
        OBS.SetScene(sceneName,False)

    def setSourceGamma(self,command):

        try:
            sourceName = " ".join(command[:(len(command)-1)])
            value = int(command[len(command)-1])
        except:
            return

        sceneElement = OBS.GetSceneElement()
        sourcesElement = sceneElement.GetElement("sources")
        gameElement = sourcesElement.GetElement(sourceName)
        if not gameElement:
            return
        globalSource = gameElement.GetString("class")
        if globalSource == "GlobalSource":
            print("got a global source")
            globalSourceName = gameElement.GetElement("data").GetString("name")

            globalElement = OBS.GetGlobalSourceListElement()

            sourceElement = globalElement.GetElement(globalSourceName)
            sourceElement.GetElement("data").SetInt("gamma",value)
            # you will need to go into the properties of the source to update
            # the gamma not sure why, obsv1 handels global sources weirdly
        else:
            v = gameElement.GetElement("data").SetInt("gamma",value)
            #let chat know that the setting change has been made
            self.qSend.put("Set "+sourceName+" gamma to " + str(value) + " ( Cooldown "+ str(self.commandCooldown) + " seconds )")
            self.lastCommand = time.time() + self.commandCooldown 

        OBS.EnterSceneMutex()
        OBS.GetScene().GetSceneItemByName(sourceName).UpdateSettings()
        OBS.LeaveSceneMutex()

    def processCommand(self,command):        

        commandName = command[1]
        remaining = command[2:]
        print(commandName)
        if commandName in self.commandToFunc:
            self.commandToFunc[commandName](remaining)
            
    
    def Tick(self,seconds):
        while not self.qRecv.empty():
            msg = self.qRecv.get().split()            
            if msg[0] == "!obs" and time.time() > self.lastCommand:                
                self.processCommand(msg)
                
    def BeginScene(self):
        pass



class gui:
    def __init__(self,config):
        defaultWidth = 0
        defaultHeight = 0
        parent = config.GetParent()

        #This setting allows the source to reload the script when you disable
        # or enable the script. Useful for development
        config.SetInt("Debug",1)

        #you are expected to reset the width and height
        #to the render size for scaling to work after properties
        parent.SetFloat("cx",defaultWidth)
        parent.SetFloat("cy",defaultHeight)

        
