
import threading
import time
import socket
import select
import Queue
import random
import logging
from anytree import AnyNode
from message import Message
from exceptions import AttributeError
logger = logging.getLogger(__name__)
BUFFER_SIZE = 1024
TCP_IP = '127.0.0.1'
BUFFER_SIZE = 1024
ROUND_TIMEOUT_S = 5

class GeneralParameters():
    def __init__(self, recievingPort, isTraitor, testComms=False):
        self.port = recievingPort
        self.isTraitor = isTraitor
        self.testComms = testComms

class GeneralProcess(threading.Thread):
    def __init__(self, name, problemStructureDict):
        threading.Thread.__init__(self, name=name)
        self.shutdownFlag = threading.Event()
        self.port = problemStructureDict[name].port
        self._is_traitor=problemStructureDict[name].isTraitor
        self._testComms=problemStructureDict[name].testComms
        self.receiveQueue = Queue.Queue(maxsize=0)
        self.sendQueue = Queue.Queue(maxsize=0)
        self.listenThread = self._ReceiveingThread("%s-listener" % self.name, self.port, self.receiveQueue)
        self.sendThread = self._SendingThread("%s-sender" % self.name, self.port, self.sendQueue)
        self.others = problemStructureDict.copy()
        if self.others.pop(self.name) is None:
            raise AttributeError("Did not find self in soluton")
        #Initialize self state
        self._state=None
        self._round=-1
        self._roundTime=None
        self._maxRound = len(self.others) - 2
        self._decision=None
        self._decisionTree=None

    def getState(self):
        return self._state

    def performOrder(self, value):
        logger.info("%s performing order: %s", self.name, value)
        self._state = "OrderSent"
        self._decision = value
        #todo implement traitor
        order = Message(self.name,self._decision, [self.name])
        for lieutenant in self.others:
            self.sendDecision(order, self.others[lieutenant])

    def getDecision(self):
        return self._decision

    def updateTree(self, message):
        value = message.value
        path = message.path
        if isinstance(path, str):
            raise ValueError
        #Initialize the tree if needed
        if self._decisionTree is None:
            self._decisionTree = AnyNode(id=path[0], dval=value,oval=None, dbg_real=len(path) == 1)
            return
        #Take node from root:
        tmpNode=self._decisionTree
        #Sanity check if the id is correct for origin general
        if tmpNode.id != path[0]:
            logger.error("Invalid ID of root node %s != %s", tmpNode.id, path[0])
            return
        #Check if all path nodes exist, if not add fake values
        for i in range(len(path) - 1):
            children = tmpNode.children
            exists=False
            for c in children:
                if c.id == path[i]:
                    #This path piece exists, continue
                    tmpNode = c
                    exists=True
                    continue
            if not exists:
                #If got here, need to add tree child as it does not exist
                tmpNode = AnyNode(id=path[i],parent=tmpNode, dval=value, oval=None, dbg_real=False)
                logger.debug("Adding fake node at path %s (id=%s)", path[:i+1], path[i])

        #Finally add the leaf to the tree (after checking if the children exist)
        exists=False
        children = tmpNode.children
        for c in children:
            if c.id == path[-1]:
                # This path piece exists! just update the value
                tmpNode = c
                exists = True
                continue
        if exists:
            tmpNode.dval = value
            tmpNode.dbg_real=True
        else:
            newNode = AnyNode(id=path[-1], parent=tmpNode, dval=value, oval=None, dbg_real=True)


    def findLevel(self, n):
        l = []

        if(self._decisionTree.height < n):
            return None
        l.append(self._decisionTree)
        for i in range(n):
            pom = []
            for c in l:
                pom.extend(c.children)
            l = pom
        return l

    def exploreTree(self):
        n = self._decisionTree.height

        for i in reversed(range(n)):
            print i
            l = self.findLevel(i)
            for e in l:
                fs = 0
                if len(e.children) == 0:
                    e.oval = e.dval
                for c in e.children:
                    if c.oval is None:
                        c.oval = c.dval
                    if c.oval is False:
                        fs += 1
                    else:
                        fs -= 1
                if fs > 0:
                    e.oval = False
                elif fs < 0:
                    e.oval = True
                else:
                    e.oval = e.dval

        self._decision = self._decisionTree.oval

        return self._decision


    def getChildMessages(self, message):
        newPath = message.path
        newPath.append(self.name)
        messages = []
        for key in self.others:
            if key == self._decisionTree.id:
                #Skip sending to general
                continue
            if key not in newPath:
                #Skip sending to paths forming cycles
                messages.append(Message(self.name, message.value, newPath))
        return messages

    def run(self):
        self.listenThread.start()
        self.sendThread.start()
        t=threading.current_thread()
        self._state="Idle"
        # Main solution loop
        while not self.shutdownFlag.is_set():

            #print "MainLoop %s" % self.name
            data = self.getMessage()
            if self._testComms:
                if data is not None:
                    logger.info("%s received : %s", self.name, data)
                # Send a random message to someone else
                if random.randint(0,5) == 5:
                    receiveingGeneral = random.choice(self.others.keys())
                    self.sendMessage("Message to %s from %s" % (receiveingGeneral, self.name), self.others[receiveingGeneral].port)
                elif random.randint(0,5) == 5:
                    self.sendMessage("Message to self %s from %s" % (self.name, self.name),
                                     self.port)
            else:
                #Main program activity
                message = None
                if data is not None:
                    message = Message.parseString(data)
                    print message.path

                    #State machine
                    if self._state == "Idle":
                        logger.info("Entering phase 1 of converging (%s)", self.name)
                        self._state= "Converging"
                        if len(message.path) != 1:
                            logger.warn("%s skipped multiple rounds of solution (to %d)", self.name, len(message.path))
                        self._round = len(message.path)
                        self.updateTree(message)
                        # update state tree and forward child messages to other processes
                        # Also send the message to self (update tree for self value)
                        tmpPath = message.path[:]
                        tmpPath.append(self.name)
                        selfMessage = Message(self.name, message.value, tmpPath)
                        self.updateTree(selfMessage)

                        childMessages = self.getChildMessages(message)
                        for msg in childMessages:
                            self.sendDecision(msg, self.others[msg.path[-1]])

                        #start timeout timer for next rounds
                        self._roundTime = time.time()

                    elif self._state == "Converging":
                        pass
                else:
                    if self._state == "Converging":
                        if time.time() - self._roundTime > ROUND_TIMEOUT_S:
                            logger.info("Timeout reached for %s in round %d", self.name, self._round)
                            #Do we send remaining messages??


        #Cleanup worker threads
        #self.sendQueue.join()
        self.sendThread.shutdownFlag.set()
        self.listenThread.shutdownFlag.set()
        self.listenThread.join()
        self.sendThread.join()

    def sendDecision(self, msg, target):
        self.sendMessage(msg.packObject(), target.port)

    def sendMessage(self, msg, targetId):
        # Put the targetId / message tuple to the queue
        self.sendQueue.put((targetId, msg))

    def getMessage(self):
        try:
            data = self.receiveQueue.get(True, 0.1)
            # Waits for 0.1 seconds, otherwise throws `Queue.Empty`
        except Queue.Empty:
            data = None
        return data

    class _ReceiveingThread(threading.Thread):

        def __init__(self, name, port, receiveQueue):
            threading.Thread.__init__(self, name=name)
            self.shutdownFlag = threading.Event()
            self.port = port
            self.queue = receiveQueue

        def run(self):
            t = threading.current_thread()
            #Based on https://steelkiwi.com/blog/working-tcp-sockets/
            readSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            readSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            readSocket.bind((TCP_IP, self.port))
            readSocket.listen(5)
            logger.debug("%s Listening on port %d", self.name, self.port)
            inputs = [readSocket]
            outputs=[]
            message_queues = {}
            while not self.shutdownFlag.is_set():
                readable, writable, exceptional = select.select(
                    inputs, outputs, inputs,0.5)
                for s in readable:
                    if s is readSocket:
                        connection, client_address = s.accept()
                        logger.debug("Connection from {0} {1}".format(client_address,connection))
                        connection.setblocking(0)
                        inputs.append(connection)
                        message_queues[connection] = Queue.Queue()
                    else:
                        data = s.recv(BUFFER_SIZE)
                        if data:
                            #Store message data for reply
                            message_queues[s].put(data)
                            if s not in outputs:
                                outputs.append(s)
                            #process received data
                            self.queue.put(data)
                        else:
                            if s in outputs:
                                outputs.remove(s)
                            inputs.remove(s)
                            s.close()
                            del message_queues[s]

                for s in writable:
                    # handle ack response TODO
                    try:
                        next_msg = message_queues[s].get_nowait()
                    except Queue.Empty:
                        outputs.remove(s)
                    except KeyError:
                        # Connection not found - sender closed the stream
                        pass
                    else:
                        pass # Reply here

                for s in exceptional:
                    inputs.remove(s)
                    if s in outputs:
                        outputs.remove(s)
                    s.close()
                    del message_queues[s]

            logger.info("Stopping %s as you wish." % self.name)
            readSocket.close()

    class _SendingThread(threading.Thread):

        def __init__(self, name, port, sendQueue):
            threading.Thread.__init__(self, name=name)
            self.shutdownFlag = threading.Event()
            self.port = port
            self.queue = sendQueue

        def run(self):

            t = threading.current_thread()
            while not self.shutdownFlag.is_set():
                try:
                    item = self.queue.get(block=True, timeout=0.1)
                    self.sendMessage(item[0], item[1])
                    self.queue.task_done()
                except Queue.Empty:
                    pass

            logger.info("Stopping %s as you wish." % self.name)


        def sendMessage(self, port, msg):
            # For now connect on each message send (will be improved in the future to maintain connections)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.connect((TCP_IP, port))
                s.send(msg)
                logger.debug( "Send message to port %d" % port)
            except socket.error as e:
                logger.debug("Exception while sending (%d -> %d) ::%s" % (self.port, port,e))
                return
            s.close()