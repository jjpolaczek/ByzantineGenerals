
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
def byzantineTest(no_generals, no_traitors):
    problemStructure={}
    generals=[]
    try:
        #Create traitors listing:
        traitors=random.sample(range(no_generals), no_traitors)
        print "Traitors are", traitors
        for i in range(no_generals):
            problemStructure["General_%d" % i] = GeneralParameters(recievingPort = 39000 + i, isTraitor=(i in traitors))
        for gen_name in problemStructure:
            generals.append(GeneralProcess(gen_name, problemStructure))

        for gen in generals:
            gen.start()

        for gen in generals:
            while gen.getState() != "Idle":
                time.sleep(0.1)
        #Pick a random general ro pass the decision to the network
        #selection=random.choice(range(no_generals))
        selection=0
        print "Selected %s to be a commanding general" % generals[selection].name
        #Pick random decision to be made
        decision = random.choice([False, True])
        print "Selected %s to be the decision" % decision
        #Execute the order
        generals[selection].performOrder(decision)
        #wait for convergence
        timeoutMax = time.time() + generals[selection]._timeoutS + 5

        while time.time() < timeoutMax:
            time.sleep(1)
            working = False
            for gen in generals:
                if gen.getState() not in ["Converged", "OrderSent"]:
                    working = True
            if not working:
                print "Completed in %f seconds" % (timeoutMax - time.time())
                break

        for gen in generals:
            logger.info("%s state: %s, decision %s", gen.name, gen.getState(),gen._decision)

        for gen in generals:
            gen.shutdownFlag.set()

        for gen in generals:
            gen.join()

    except ServiceExit:
        for gen in generals:
            gen.shutdownFlag.set()

        for gen in generals:
            gen.join()

def main():
    # Register the signal handlers
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, service_shutdown)
    signal.signal(signal.SIGINT, service_shutdown)
    #testComms(5)
    byzantineTest(9, 0)


#proc = GeneralProcess("Hello")
#proc.start()
#time.sleep(10)
#proc.do_run=False
#proc.join()

if __name__ == '__main__':
    main()