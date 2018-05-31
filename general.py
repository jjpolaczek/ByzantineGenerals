
import threading
import time
import socket
import select
import Queue
import random
import logging
from anytree import AnyNode, RenderTree
from message import Message
from exceptions import AttributeError
import copy
logger = logging.getLogger(__name__)
BUFFER_SIZE = 1024
TCP_IP = '127.0.0.1'
BUFFER_SIZE = 1024
DEFAULT_DECISION=False
class GeneralParameters():
    def __init__(self, recievingPort, sendingPort, isTraitor, failureRate=0.0, latency_ms=0, latency_variance_ms=0,  testComms=False):
        self.port = recievingPort
        self.sPort = sendingPort
        self.isTraitor = isTraitor
        self.failureRate = failureRate
        self.latency = latency_ms / 1000.0
        self.latencyVar = latency_variance_ms / 1000.0
        self.testComms = testComms

class GeneralProcess(threading.Thread):
    def __init__(self, name, problemStructureDict):
        threading.Thread.__init__(self, name=name)
        self.shutdownFlag = threading.Event()
        self._config = problemStructureDict[name]
        self.receiveQueue = Queue.Queue(maxsize=0)
        self.sendQueue = Queue.Queue(maxsize=0)
        self.listenThread = self._ReceiveingThread("%s-listener" % self.name, self._config.port, self.receiveQueue)
        self.sendThread = self._SendingThread("%s-sender" % self.name, self._config.sPort, self.sendQueue, self._config)
        self.others = problemStructureDict.copy()
        self._maxFaulty = int((len(self.others) - 1) / 3.0)
        if self.others.pop(self.name) is None:
            raise AttributeError("Did not find self in soluton")
        #Initialize self state
        self._state=None
        self._maxMessages = self._getMaxMessages(len(self.others) + 1)
        self._timeoutS = float(self._maxMessages) * 0.05 + 1
        logger.info("Timeout set to %f seconds", self._timeoutS)
        self._timeoutTime = 0
        self._decision=None
        self._givenOrder=None
        self._decisionTree=None


        self._debugCounter=0
        self._uniqueUpdates=0

    def _getMaxMessages(self, generals):
        # First message (order)
        # count = generals - 1
        #1 for the general
        count = 1
        # Subsequent messages
        round = 1
        depth = self._maxFaulty
        if depth == 0:
            depth +=1
        for i in range(1, depth + 1):
            tmp = 1
            for j in range(1, i+1, 1):
                tmp *= (generals - j)
            count += tmp
        return count

    def getState(self):
        return self._state

    def performOrder(self, value):
        logger.info("%s performing order: %s", self.name, value)
        self._state = "OrderSent"
        self._decision = value
        fakeValue = not self._decision
        order = Message(self.name,self._decision, [self.name])
        fakeOrder = Message(self.name, fakeValue, [self.name])

        for lieutenant in self.others:
            self.sendDecision(order, self.others[lieutenant])

    def getDecision(self):
        return self._decision

    def debugStateTree(self):
        #Explore and print tree state
        if self._decisionTree is None:
            #logger.warn("Decision Tree of %s empty! Cannot print", self.name )
            print "Decision Tree of %s empty! Cannot print" % self.name
            return

        def printNode(node, indent):
            indentStr = indent * "\t"
            print "%sNode_ID: %s, parent: %s, dval=%s, oval=%s" % (indentStr, node.id, node.parent, node.dval, node.oval)

        print "Printing tree of %s" % self.name

        #indent = 0
        #tmpNode = self._decisionTree
        #printNode(tmpNode, indent)
        for pre, _, node in RenderTree(self._decisionTree):
            if len(node.children) == 0:
                print("%s%s --  (%s) IN: %s," % (pre, node.id, node.dbg_real, node.dval))
            else:
                print("%s%s --%s---- OUT: %s," % (pre, node.id, node.dval,node.oval))

    def updateTree(self, message):
        value = message.value
        path = message.path
        if isinstance(path, str):
            raise ValueError
        #Initialize the tree if needed
        if self._decisionTree is None:
            #logger.debug("(%s) adding root %s", self.name, path)
            self._decisionTree = AnyNode(id=path[0], dval=None,oval=None, dbg_real=len(path) == 1)
            tmpNode= self._decisionTree
            for nodeName in path[1:]:
                #If last element:
                if nodeName == path[-1]:
                    tmpNode = AnyNode(id=nodeName, parent=tmpNode, dval=value, oval=None, dbg_real=True)
                else:
                    tmpNode = AnyNode(id=nodeName, parent=tmpNode,  dval=None,oval=None, dbg_real=False)
            self._uniqueUpdates += 1
            return
        #Take node from root:
        tmpNode=self._decisionTree
        #Sanity check if the id is correct for origin general
        if tmpNode.id != path[0]:
            logger.error("Invalid ID of root node %s != %s", tmpNode.id, path[0])
            return
        #Check if all path nodes exist, if not add fake values

        for i in range(1,len(path) - 1, 1):
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
                tmpNode = AnyNode(id=path[i],parent=tmpNode, dval=None, oval=None, dbg_real=False)
                #logger.debug("(%s)Adding fake node at path %s (id=%s) %s", self.name, path[:i+1], path[i], path)

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
            logger.warn("(%s)Updating node %s", self.name, path)
        else:
            #logger.debug("(%s)Adding node at path %s", self.name, path)
            newNode = AnyNode(id=path[-1], parent=tmpNode, dval=value, oval=None, dbg_real=True)
            self._uniqueUpdates += 1

    def verifyTree(self):
        #get others variable
        others = self.others.keys()
        #recursively go through the tree looking for missing permutations and filling with default value
        def checkNode(node, depth, possibleValues, path):
            path.append(node.id)
            if depth < 0:
                return 0
            possibleValues.remove(node.id)
            children = node.children
            missingValues = possibleValues[:]

            count = 0
            for child in children:
                if child.id in missingValues:
                    missingValues.remove(child.id)
                    count += checkNode(child, depth - 1, possibleValues[:], path[:])

            for missing in missingValues:
                logger.debug("%s depth %d, %s", self.name, depth, path)
                newNode = AnyNode(id=missing, parent=node, dval=DEFAULT_DECISION, oval=None, dbg_real=False)
                count += checkNode(newNode, depth - 1, possibleValues[:], path[:]) + 1
            return count

        maxDepth = self._maxFaulty
        if maxDepth > 0:
            maxDepth -= 1
        corrections = checkNode(self._decisionTree, maxDepth, others, [])
        if corrections > 0:
            logger.warn("%s made %d corrections", self.name, corrections)

    def findLevel(self, level):
        nodesAtLevel = []
        if(self._decisionTree.height < level):
            return None
        nodesAtLevel.append(self._decisionTree)
        for i in range(level):
            tmp = []
            for c in nodesAtLevel:
                tmp.extend(c.children)
            nodesAtLevel = tmp
        return nodesAtLevel

    def exploreTree(self):
        self.verifyTree()
        n = self._decisionTree.height
        # print "exploreTree, height {0}".format(n)

        for i in reversed(range(n + 1)):
            nodesAtLevel = self.findLevel(i)
            for node in nodesAtLevel:
                votesFalse = 0
                if len(node.children) == 0:
                    node.oval = node.dval

                for c in node.children:
                    if c.oval is None:
                        logger.error("%s Could not find output value of node %s at level %s", self.name, c.id, i)
                    if c.oval is False:
                        votesFalse += 1
                    else:
                        votesFalse -= 1
                #Count value of self dval in majority vote
                if False:
                    if node.dval is False:
                        votesFalse += 1
                    elif node.dval is True:
                        votesFalse -= 1
                        # print "c.dval: {0}, c.oval: {1}".format( c.dval,c.oval)

                if len(node.children) == 0:
                    pass
                elif votesFalse > 0:
                    node.oval = False
                elif votesFalse < 0:
                    node.oval = True
                else:
                    #Defalt decision if if unsure
                    node.oval = DEFAULT_DECISION

        self._decision = self._decisionTree.oval
        # print "decyzja",self._decision
        return self._decision


    def getChildMessages(self, message):
        messages = []
        #Second condition is to limit recursion depth
        maxDepth = self._maxFaulty
        if maxDepth == 0:
            maxDepth += 1
        if self.name not in message.path and len(message.path) <= maxDepth:
            newPath = message.path[:]
            newPath.append(self.name)
            debug = []
            for key in self.others:
                if key == message.path[0]:
                    #Skip sending to general
                    continue
                # broadcast to all others
                messages.append((key, Message(self.name, message.value, newPath)))
                debug.append(key)
            #also prepare sending to self
            messages.append((self.name, Message(self.name, message.value, newPath)))
            debug.append(self.name)
            #logger.warn(" %s -----%s sending %s to %s", message.value, self.name, newPath, debug)
        return messages

    def run(self):
        self.listenThread.start()
        self.sendThread.start()
        t=threading.current_thread()

        timeout=time.time() + 5.0 # Give 5 seconds for process to start
        while self.listenThread.getState() != "Idle" and self.sendThread.getState() != "Idle":
            time.sleep(0.1)
            if time.time() > timeout:
                logger.error("Timout exceeded for %s", self.name)

        self._state="Idle"
        # Main solution loop
        while not self.shutdownFlag.is_set():

            #print "MainLoop %s" % self.name
            data = self.getMessage()
            if self._config.testComms:
                if data is not None:
                    logger.info("%s received : %s", self.name, data)
                # Send a random message to someone else
                if random.randint(0,5) == 5:
                    receiveingGeneral = random.choice(self.others.keys())
                    self.sendMessage("Message to %s from %s" % (receiveingGeneral, self.name), self.others[receiveingGeneral].port)
                elif random.randint(0,5) == 5:
                    self.sendMessage("Message to self %s from %s" % (self.name, self.name),
                                     self._config.port)
            else:
                #Main program activity
                message = None
                if data is not None:
                    message = Message.parseString(data)

                    logger.debug("%s msg with path %s", self.name, message.path)
                    #print message.path
                    self._debugCounter += 1
                    #logger.info("Got message with path %s (%s)", message.path, self.name)
                    #State machine
                    if self._state == "Idle":
                        logger.info("Entering phase 1 of converging (%s)", self.name)
                        self._state= "Converging"
                        self._givenOrder = message.value
                        if len(message.path) != 1:
                            logger.warn("%s skipped multiple rounds of solution (to %d)", self.name, len(message.path))
                        #self.updateTree(message)

                        # First send the message to self (update tree for self value)
                        self.updateTree(message)
                        # update state tree and forward child messages to other processes
                        childMessages = self.getChildMessages(message)
                        for msg in childMessages:
                            if msg[0] == self.name:
                                #Do not need to send msd to self
                                self.updateTree(msg[1])
                            else:
                                self.sendDecision(msg[1], self.others[msg[0]])

                        #start timeout timer for next rounds
                        self._timeoutTime = time.time() + self._timeoutS

                    elif self._state == "Converging":
                        # First send the message to self (update tree for self value)

                        self.updateTree(message)
                        # update state tree and forward child messages to other processes
                        childMessages = self.getChildMessages(message)
                        for msg in childMessages:
                            if msg[0] == self.name:
                                #Do not need to send msd to self
                                self.updateTree(msg[1])
                            else:
                                self.sendDecision(msg[1], self.others[msg[0]])

                else:
                    if self._state == "Converging":
                        if time.time() > self._timeoutTime:
                            logger.warn("Timeout reached for %s  exchanged %d messages (%d)", self.name, self._uniqueUpdates, self._maxMessages)
                            self._decision = self.exploreTree()

                            self._state = "Converged"
                            #Do we send remaining messages??
                        if self._uniqueUpdates == self._maxMessages:
                            logger.info("Convergence for %s  exchanged %d messages (%d)", self.name, self._uniqueUpdates, self._maxMessages)
                            self._decision = self.exploreTree()

                            self._state = "Converged"



        #Cleanup worker threads
        #self.sendQueue.join()
        self.sendThread.shutdownFlag.set()
        self.listenThread.shutdownFlag.set()
        self.listenThread.join()
        self.sendThread.join()

    def sendDecision(self, msg, target):
        # logger.info("%s is sending to %s, path:", self.name, target)
        if self._config.isTraitor:
            if bool(random.getrandbits(1)):
                msg.value = not msg.value
        self.sendMessage(msg.packObject(), target.port)

    def sendMessage(self, msg, targetId):
        # Put the targetId / message tuple to the queue
        self.sendQueue.put((targetId, msg, time.time()))

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
            self.state = None

        def getState(self):
            return self.state
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
            self.state="Idle"
            while not self.shutdownFlag.is_set():
                readable, writable, exceptional = select.select(
                    inputs, outputs, inputs,0.5)
                for s in readable:
                    if s is readSocket:
                        connection, client_address = s.accept()
                        #logger.debug("{2}: Connection from {0} {1}".format(client_address,connection, self.name))
                        connection.setblocking(0)
                        inputs.append(connection)
                        message_queues[connection] = Queue.Queue()
                    else:
                        data = s.recv(BUFFER_SIZE)
                        if data:
                            #logger.debug("{2}: Data from {0} {1}".format(client_address, connection, self.name))
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

            logger.debug("Stopping %s as you wish." % self.name)
            readSocket.close()

    class _SendingThread(threading.Thread):

        def __init__(self, name, port, sendQueue, config):
            threading.Thread.__init__(self, name=name)
            self.shutdownFlag = threading.Event()
            self.port = port
            self.queue = sendQueue
            self._config = config
            self.waitList = []
            self.state=None
        def getState(self):
            return self.state

        def run(self):
            t = threading.current_thread()
            self.state="Idle"
            while not self.shutdownFlag.is_set():
                try:
                    #This is perhaps not the moste efficient way to do it but simulates the network fairly well...
                    #item is: (port, message, timestamp)
                    item = self.queue.get(block=True, timeout=0.1)
                    #Add random variance to timeout
                    latencyVariance = random.uniform(-self._config.latencyVar, self._config.latencyVar)
                    if (item[2] + self._config.latency + latencyVariance) > time.time():
                        #Creating new item tuple to pass the same latency variance
                        self.waitList.append((item[0], item[1], item[2] + latencyVariance))
                    else:
                        self.sendMessage(item[0], item[1])
                except Queue.Empty:
                    if len(self.waitList) > 0:
                        #Get values over timeout value
                        toSend = [s for s in self.waitList if ((s[2] + self._config.latency) < time.time())]
                        #Update the list of waiting messages
                        newWaitList = []
                        for item in self.waitList:
                            if item not in toSend:
                                newWaitList.append(item)
                        self.waitList = newWaitList
                        #Send the required messages
                        for msg in toSend:
                            self.sendMessage(msg[0], msg[1])

            logger.debug("Stopping %s as you wish." % self.name)


        def sendMessage(self, port, msg):
            #Logic to drop messages based on failure ratio:
            #logger.debug("%s sending message", self.name)
            if self._config.failureRate > random.random():
                self.queue.task_done()
                return
            # For now connect on each message send (will be improved in the future to maintain connections)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.connect((TCP_IP, port))
                s.send(msg)
                self.queue.task_done()
                #logger.debug( "Send message to port %d" % port)
            except socket.error as e:
                logger.error("Exception while sending (%d -> %d) ::%s" % (self.port, port,e))
                s.close()
                return
            s.close()