
from general import GeneralProcess, GeneralParameters
from message import Message
import time
import signal
import random
import logging
logger = logging.getLogger(__name__)
#msg = Message()
#print "Hello"
#print msg.packObject()

class ServiceExit(Exception):
    """
    Custom exception which is used to trigger the clean exit
    of all running threads and the main program.
    """
    pass

def service_shutdown(signum, frame):
    print('Caught signal %d' % signum)
    raise ServiceExit

def testComms(no_generals):
    problemStructure={}
    generals=[]
    try:
        for i in range(no_generals):
            problemStructure["General_%d" % i] = GeneralParameters(recievingPort=39000 , sendingPort=39100 + i, isTraitor=False, testComms=True)
        for gen_name in problemStructure:
            generals.append(GeneralProcess(gen_name, problemStructure))
        for gen in generals:
            gen.start()
        time.sleep(10)
        for gen in generals:
            gen.shutdownFlag.set()

        for gen in generals:
            gen.join()

    except ServiceExit:
        for gen in generals:
            gen.shutdownFlag.set()

        for gen in generals:
            gen.join()

class TestSolution():
    def __init__(self, basePort=37000):
        self.generals = []
        self.traitors= []
        self.problemStructure = {}
        self.commanderNum = None
        self.basePort = basePort

    def _setup(self, no_generals, no_traitors, latencyAvgms=0, latencyDiffms=0):
        # Create traitors listing:
        traitors = random.sample(range(no_generals), no_traitors)
        logger.debug("Traitors are %s", self.traitors)
        for i in range(no_generals):
            self.problemStructure["General_%d" % i] = GeneralParameters(recievingPort=self.basePort + i,sendingPort=self.basePort + i + 100, isTraitor=(i in traitors), latency_ms=latencyAvgms, latency_variance_ms=latencyDiffms)
            #Append traitor names
            if i in traitors:
                self.traitors.append("General_%d" % i)
        for gen_name in self.problemStructure:
            self.generals.append(GeneralProcess(gen_name, self.problemStructure))

    def _start(self, timeout=10):
        for gen in self.generals:
            gen.start()
        t0 = time.time()
        for gen in self.generals:
            while gen.getState() != "Idle":
                time.sleep(0.1)
                if (t0 + timeout) < time.time():
                    break
            if gen.getState() != "Idle":
                raise Exception("Timeout in init reached")

    def _cleanup(self):
        for gen in self.generals:
            gen.shutdownFlag.set()
        for gen in self.generals:
            gen.join()
        #reset state
        self.__init__(self.basePort)
    def _converge(self, timeout):
        timeoutMax = time.time() + timeout

        while time.time() < timeoutMax:
            time.sleep(1)
            working = False
            for gen in self.generals:
                if gen.getState() not in ["Converged", "OrderSent"]:
                    working = True
            if not working:
                logger.debug("Completed in %f seconds" % (timeoutMax - time.time()))
                break
        #Final check
        working = False
        for gen in self.generals:
            if gen.getState() not in ["Converged", "OrderSent"]:
                working = True
        if working:
            logger.error("Did not converge in %f seconds", timeout)
            raise Exception("Convergence did not finish")
    def _verify(self):
        #IC1.All loyal lieutenants obey the same order.
        decisions = []
        for gen in self.generals:
            # skip lieutenant
            if gen.name != self.generals[self.commanderNum].name:
                if gen.name not in self.traitors:
                    decisions.append(gen.getDecision())
        #If there is not one unique decision it will state false
        IC1 = len(set(decisions)) == 1
        #IC2. If the commanding general is loyal then every loyal lieutenant obeys the same order he sends
        if self.generals[self.commanderNum].name not in self.traitors:
            commanderDec = self.generals[self.commanderNum].getDecision()
            #same logic but for commander decision added
            IC2 = len(set(decisions + [commanderDec])) == 1
        else:
            #If commanding general is selected traitor
            IC2 = None
        return (IC1, IC2)

    def _printIfFail(self, result):
        if (result[0] is not True) or (result[1] not in [None, True]):
            failed = True
            logger.warn("Failed Conditions for %d generals and %d traitors", len(self.generals), len(self.traitors))
            logger.warn("Commander: %s", self.generals[self.commanderNum].name)
            logger.warn("Traitors: %s", self.traitors)
            for gen in self.generals:
                logger.info("%s state: %s, decision %s", gen.name, gen.getState(), gen._decision)
                gen.debugStateTree()
                time.sleep(0.5)
    def byzantineTest(self, no_generals, no_traitors):
        result=None
        tstart = time.time()
        logger.info("Simulation for %d generals and %d traitors", no_generals, no_traitors)
        try:
            self._setup(no_generals, no_traitors)
            self._start()
            #Pick a random general ro pass the decision to the network
            selection=random.choice(range(no_generals))
            logger.debug( "Selected %s to be a commanding general" % self.generals[selection].name)
            self.commanderNum = selection
            #Pick random decision to be made
            decision = random.choice([False, True])
            logger.debug("Selected %s to be the decision" % decision)
            #Execute the order
            self.generals[selection].performOrder(decision)
            #wait for convergence
            self._converge(self.generals[0]._timeoutS + 10)
            result = self._verify()
            logger.info("IC1: %s, IC2: %s" % result)
            self._printIfFail(result)
            if False:
                for gen in self.generals:
                    logger.info("%s state: %s, decision %s", gen.name, gen.getState(), gen._decision)
                    gen.debugStateTree()
                    time.sleep(0.5)
            self._cleanup()
        except ServiceExit:
            self._cleanup()
        except Exception as e:
            logger.error("Caught unexpected exception in the test: %s", e)
            self._cleanup()
        logger.info("Completed in %fs", time.time() - tstart)
        return result

    def byzantineTestCommanderTraitor(self, no_generals, no_additional_traitors):
        no_traitors = no_additional_traitors + 1
        result = None
        tstart = time.time()
        logger.info("Simulation for %d generals and %d traitors with commander forced to be traitor", no_generals, no_traitors)
        try:
            self._setup(no_generals, no_traitors)
            self._start()
            # Pick a traitor to be a general ro pass the decision to the network
            selection = 0
            for gen in self.generals:
                if gen.name in self.traitors:
                    break
                else:
                    selection += 1
            logger.debug("Selected %s to be a commanding (traitor) general" % self.generals[selection].name)
            self.commanderNum = selection
            # Pick random decision to be made
            decision = random.choice([False, True])
            logger.debug("Selected %s to be the decision" % decision)
            # Execute the order
            self.generals[selection].performOrder(decision)
            # wait for convergence
            self._converge(self.generals[0]._timeoutS + 10)
            result = self._verify()
            logger.info("IC1: %s, IC2: %s" % result)
            self._printIfFail(result)

            self._cleanup()
        except ServiceExit:
            self._cleanup()
        except Exception as e:
            logger.error("Caught unexpected exception in the test: %s", e)
            self._cleanup()
        logger.info("Completed in %fs", time.time() - tstart)
        return result

    def byzantineTestWithLatency(self, no_generals, no_traitors, latencyMin, latencyMax):
        result=None
        tstart = time.time()
        logger.info("Simulation for %d generals and %d traitors with latency from %dms to %dms", no_generals, no_traitors, latencyMin, latencyMax)
        try:
            self._setup(no_generals, no_traitors, (latencyMax + latencyMin) / 2.0, latencyMax - latencyMin)
            self._start()
            #Pick a random general ro pass the decision to the network
            selection=random.choice(range(no_generals))
            logger.debug( "Selected %s to be a commanding general" % self.generals[selection].name)
            self.commanderNum = selection
            #Pick random decision to be made
            decision = random.choice([False, True])
            logger.debug("Selected %s to be the decision" % decision)
            #Execute the order
            self.generals[selection].performOrder(decision)
            #wait for convergence
            self._converge(self.generals[0]._timeoutS + 10)
            result = self._verify()
            logger.info("IC1: %s, IC2: %s" % result)
            self._printIfFail(result)

            self._cleanup()
        except ServiceExit:
            self._cleanup()
        except Exception as e:
            logger.error("Caught unexpected exception in the test: %s", e)
            self._cleanup()
        logger.info("Completed in %fs", time.time() - tstart)
        return result
def main():
    # Register the signal handlers
    logging.basicConfig(level=logging.WARN)
    logging.getLogger('__main__').setLevel(logging.INFO)
    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)
    #Create test object and run tests
    tester = TestSolution()
    generalCountTested = range(3, 8)
    retries = 2
    #return
    #tester.byzantineTest(4, 1)
    #tester.byzantineTest(4, 1)
    #return
    #Basic testing loop for traitorous and faithful generals
    for gen_count in generalCountTested:
        #3m +1 generals cope with m traitors so
        # for k generals we can have (k - 1) / 3 traitors rounded down
        max_traitors = int((gen_count - 1) / 3.0)
        for traitors in range(0, max_traitors + 1):
            for retry in range(retries):
                tester.byzantineTest(gen_count, traitors)

    # Testing loop for traitorous commanding generals
    retries = 2
    generalCountTested = range(4, 8)
    for gen_count in generalCountTested:
        #3m +1 generals cope with m traitors so
        # for k generals we can have (k - 1) / 3 traitors rounded down
        additional_traitors = int((gen_count - 1) / 3.0) - 1 # this will not work for general count below 4 (al least 1 traitor must be)
        for traitors in range(0, additional_traitors + 1):
            for retry in range(retries):
                tester.byzantineTestCommanderTraitor(gen_count, traitors)

    # Testing loop for traitorous commanding generals with latency
    retries = 2
    generalCountTested = range(4, 8)
    latencyMin_ms = 100
    latencyMax_ms = 300
    for gen_count in generalCountTested:
        #3m +1 generals cope with m traitors so
        # for k generals we can have (k - 1) / 3 traitors rounded down
        max_traitors = int((gen_count - 1) / 3.0)
        for traitors in range(0, max_traitors + 1):
            for retry in range(retries):
                tester.byzantineTestWithLatency(gen_count, traitors, latencyMin_ms, latencyMax_ms)
if __name__ == '__main__':
    main()