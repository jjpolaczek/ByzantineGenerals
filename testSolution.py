
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
            problemStructure["General_%d" % i] = GeneralParameters(recievingPort = 38000 + i, isTraitor=False, testComms=True)
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
    def __init__(self, basePort=39000):
        self.generals = []
        self.traitors= []
        self.problemStructure = {}
        self.commanderNum = None
        self.basePort = basePort

    def _setup(self, no_generals, no_traitors, failModes):
        # Create traitors listing:
        traitors = random.sample(range(no_generals), no_traitors)
        logger.debug("Traitors are %s", self.traitors)
        for i in range(no_generals):
            self.problemStructure["General_%d" % i] = GeneralParameters(recievingPort=self.basePort + i, isTraitor=(i in traitors))
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
            if gen.name == self.generals[self.commanderNum].name:
                continue
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

    def byzantineTest(self, no_generals, no_traitors):
        result=None
        tstart = time.time()
        logger.info("Simulation for %d generals and %d traitors", no_generals, no_traitors)
        try:
            self._setup(no_generals, no_traitors, None)
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
            self._converge(self.generals[0]._timeoutS + 5)
            result = self._verify()

            logger.info("IC1: %s, IC2: %s" % result)
            for gen in self.generals:
                logger.debug("%s state: %s, decision %s", gen.name, gen.getState(), gen._decision)

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
    logging.basicConfig(level=logging.ERROR)
    logging.getLogger('__main__').setLevel(logging.INFO)
    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)
    #Create test object and run tests
    tester = TestSolution()
    generalCountTested = range(3, 8)
    retries = 3

    for gen_count in generalCountTested:
        #3m +1 generals cope with m traitors so
        # for k generals we can have (k - 1) / 3 traitors rounded down
        max_traitors = int((gen_count - 1) / 3.0)
        for traitors in range(0, max_traitors + 1):
            for retry in range(retries):
                tester.byzantineTest(gen_count, traitors)


if __name__ == '__main__':
    main()