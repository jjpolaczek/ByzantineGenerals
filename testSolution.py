
from general import GeneralProcess, GeneralParameters
from message import Message
import time
import signal
import random
import logging
import os
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
        self.basePort = basePort
        self._resetTestVariables()
        #The result logger will log result counts for keys in tuple form: (no_generals, no_traitors) and increment fail counters
        self.resetFails()


    def _resetTestVariables(self):
        self.generals = []
        self.traitors= []
        self.problemStructure = {}
        self.commanderNum = None

    def resetFails(self):
        self.resultFailLogger = {}

    def _updateFails(self, result):
        no_generals = len(self.generals)
        no_traitors = len(self.traitors)
        #Checks IC1 and IC2 conditions
        if (result[0] is not True) or (result[1] not in [None, True]):
            try:
                self.resultFailLogger[(no_generals, no_traitors)] += 1
            except KeyError:
                self.resultFailLogger[(no_generals, no_traitors)] = 1
    def saveFailsCSV(self, filename):
        with open(filename, 'wa') as f:
            f.write("sep=;" + os.linesep)
            f.write("Generals;Traitors;Fails" + os.linesep)
            for key in self.resultFailLogger:
                f.write("%d;%d;%d" %(key[0], key[1], self.resultFailLogger[key]) + os.linesep)


    def _setup(self, no_generals, no_traitors, latencyAvgms=0, latencyDiffms=0, traitorFailRate=0.0, globalFailRate=0.0):
        # Create traitors listing:
        traitors = random.sample(range(no_generals), no_traitors)
        logger.debug("Traitors are %s", self.traitors)
        for i in range(no_generals):
            failRate = globalFailRate
            if i in traitors:
                failRate = globalFailRate
            self.problemStructure["General_%d" % i] = GeneralParameters(recievingPort=self.basePort + i,sendingPort=self.basePort + i + 100,
                                                                        isTraitor=(i in traitors), latency_ms=latencyAvgms, latency_variance_ms=latencyDiffms, failureRate=failRate)
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
        self._resetTestVariables()
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
            max_traitors = int((len(self.generals) - 1) / 3.0)
            #Print only if the assumption of traitor count is not fullfilled
            if len(self.traitors) <= max_traitors:
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
            self._updateFails(result)
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
            self._updateFails(result)

            self._cleanup()
        except ServiceExit:
            self._cleanup()
        except Exception as e:
            logger.error("Caught unexpected exception in the test: %s", e)
            self._cleanup()
        logger.info("Completed in %fs", time.time() - tstart)
        return result

    def byzantineTestWithLatency(self, no_generals, no_traitors, latencyMin, latencyMax):
        result = None
        tstart = time.time()
        logger.info("Simulation for %d generals and %d traitors with latency from %dms to %dms", no_generals,
                    no_traitors, latencyMin, latencyMax)
        try:
            self._setup(no_generals, no_traitors, latencyAvgms=(latencyMax + latencyMin) / 2.0, latencyDiffms=latencyMax - latencyMin)
            self._start()
            # Pick a random general ro pass the decision to the network
            selection = 0
            for gen in self.generals:
                if gen.name not in self.traitors:
                    break
                else:
                    selection += 1
            logger.debug("Selected %s to be a commanding general" % self.generals[selection].name)
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
            self._updateFails(result)

            self._cleanup()
        except ServiceExit:
            self._cleanup()
        except Exception as e:
            logger.error("Caught unexpected exception in the test: %s", e)
            self._cleanup()
        logger.info("Completed in %fs", time.time() - tstart)
        return result

    def byzantineTestWithLinkFailsandLatency(self, no_generals, no_traitors, traitorFailRate=0.0, globalFailRate=0.0, latencyMin=0.0, latencyMax=0.0):
        result = None
        tstart = time.time()
        logger.info("Simulation for %d generals and %d traitors with traitors having %f failure rate, others %f", no_generals,
                    no_traitors, traitorFailRate, globalFailRate)
        logger.info("Latency settings from %dms to %dms", latencyMin, latencyMax)
        try:
            self._setup(no_generals, no_traitors, traitorFailRate=traitorFailRate, globalFailRate=globalFailRate,
                        latencyAvgms=(latencyMax + latencyMin) / 2.0, latencyDiffms=latencyMax - latencyMin)
            self._start()
            # Pick a random general ro pass the decision to the network
            selection = random.choice(range(no_generals))
            logger.debug("Selected %s to be a commanding general" % self.generals[selection].name)
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
            self._updateFails(result)

            self._cleanup()
        except ServiceExit:
            self._cleanup()
        except Exception as e:
            logger.error("Caught unexpected exception in the test: %s", e)
            self._cleanup()
        logger.info("Completed in %fs", time.time() - tstart)
        return result


def main():
    test_toggle={"standard": True,
           "commander_traitor": True,
           "basic_latency": True,
           "traitor_fails": True,
           "global_fails": True
           }
    # Register the signal handlers
    logging.basicConfig(level=logging.ERROR)
    logging.getLogger('__main__').setLevel(logging.INFO)
    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)
    #Create test object and run tests
    tester = TestSolution()
    generalCountTested = range(8, 11)
    retries = 100
    if test_toggle["standard"]:
        #Basic testing loop for traitorous and faithful generals
        for gen_count in generalCountTested:
            #3m +1 generals cope with m traitors so
            # for k generals we can have (k - 1) / 3 traitors rounded down, we test for more than minimum no of traitors!!!
            max_traitors = int((gen_count - 1) / 3.0) + 1
            for traitors in range(0, max_traitors + 1):
                for retry in range(retries):
                    tester.byzantineTest(gen_count, traitors)
        tester.saveFailsCSV("byzantine_standard%d.csv" % retries)
        tester.resetFails()
        return
    # Testing loop for traitorous commanding generals
    retries = 100
    generalCountTested = range(9, 11)
    if test_toggle["commander_traitor"]:
        for gen_count in generalCountTested:
            #3m +1 generals cope with m traitors so
            # for k generals we can have (k - 1) / 3 traitors rounded down
            additional_traitors = int((gen_count - 1) / 3.0) # this will not work for general count below 4 (al least 1 traitor must be)
            for traitors in range(0, additional_traitors + 1):
                for retry in range(retries):
                    tester.byzantineTestCommanderTraitor(gen_count, traitors)
        tester.saveFailsCSV("byzantine_generalTraitor%d.csv" % retries)
        tester.resetFails()
    # Testing loop for traitorous and faithful generals with latency
    retries = 0
    generalCountTested = range(9, 11)
    latencyMin_ms = 100
    latencyMax_ms = 300
    if test_toggle["basic_latency"]:
        for gen_count in generalCountTested:
            #3m +1 generals cope with m traitors so
            # for k generals we can have (k - 1) / 3 traitors rounded down
            max_traitors = int((gen_count - 1) / 3.0)
            for traitors in range(0, max_traitors + 1):
                for retry in range(retries):
                    tester.byzantineTestWithLatency(gen_count, traitors, latencyMin_ms, latencyMax_ms)
        tester.saveFailsCSV("byzantine_basicLatency%d.csv" % retries)
        tester.resetFails()

    # Testing loop for traitorous and faithful generals  with latency and failures
    retries = 100
    generalCountTested = range(9, 11)
    latencyMin_ms = 100
    latencyMax_ms = 300
    traitorFailRates = [0.2, 0.8]
    globalFailRates = [0.05, 0.1]

    if test_toggle["traitor_fails"]:
        for t_failrate in traitorFailRates:
            for gen_count in generalCountTested:
                #3m +1 generals cope with m traitors so
                # for k generals we can have (k - 1) / 3 traitors rounded down
                max_traitors = int((gen_count - 1) / 3.0) + 1
                for traitors in range(0, max_traitors + 1):
                            for retry in range(retries):
                                tester.byzantineTestWithLinkFailsandLatency(gen_count, traitors, t_failrate, 0.0,
                                                                            latencyMin_ms, latencyMax_ms)
            tester.saveFailsCSV("byzantine_tfails%.2f%d.csv" % (t_failrate, retries))
            tester.resetFails()

    if test_toggle["global_fails"]:
        for g_failrate in globalFailRates:
            for gen_count in generalCountTested:
                # 3m +1 generals cope with m traitors so
                # for k generals we can have (k - 1) / 3 traitors rounded down
                max_traitors = int((gen_count - 1) / 3.0) + 1
                for traitors in range(0, max_traitors + 1):
                    for retry in range(retries):
                        tester.byzantineTestWithLinkFailsandLatency(gen_count, traitors, 0.0, g_failrate,
                                                                    latencyMin_ms, latencyMax_ms)
            tester.saveFailsCSV("byzantine_gfails%.2f%d.csv" % (g_failrate, retries))
            tester.resetFails()

if __name__ == '__main__':
    main()