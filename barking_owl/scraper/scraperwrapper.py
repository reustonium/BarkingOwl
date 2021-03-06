import pika
import json
import uuid
from time import strftime
import time
import threading
import datetime

from scraper import Scraper

class ScraperWrapper(threading.Thread):

    def __init__(self,address='localhost',exchange='barkingowl',broadcast_interval=5,DEBUG=False):
        """
        __init__() constructor setups up the message bus, inits the thread, and sets up 
        local status variables.
        """

        threading.Thread.__init__(self)

        self.uid = str(uuid.uuid4())
        self.address = address
        self.exchange = exchange
        self.DEBUG=DEBUG
        self.interval = broadcast_interval

        # create scraper instance
        self.scraper = Scraper(uid=self.uid)
        self.scraping = False
        self.scraper_thread = None

        # stop control
        self.stopped = False

        #setup message bus
        self.respcon = pika.BlockingConnection(pika.ConnectionParameters(
                                                           host=self.address))
        self.respchan = self.respcon.channel()
        self.respchan.exchange_declare(exchange=self.exchange,type='fanout')

        self.reqcon = pika.BlockingConnection(pika.ConnectionParameters(host=address))
        self.reqchan = self.reqcon.channel()
        self.reqchan.exchange_declare(exchange=exchange,type='fanout')
        result = self.reqchan.queue_declare(exclusive=True)
        queue_name = result.method.queue
        self.reqchan.queue_bind(exchange=exchange,queue=queue_name)
        self.reqchan.basic_consume(self._reqcallback,queue=queue_name,no_ack=True)

        # start our anouncement of availiability
        threading.Timer(self.interval, self.broadcast_available).start()

        if self.DEBUG:
            print "Scraper Wrapper INIT complete."

    def run(self):
        """
        run() is called by the threading sub system when ScraperWrapper.start() is called.  This function
        sets up all of the call abcks needed, as well as begins consuming on the message bus. 
        """
        # setup call backs
        self.scraper.set_finished_callback(self.scraper_finished_callback)
        self.scraper.set_started_callback(self.scraper_started_callback)
        self.scraper.set_broadcast_document_callback(self.scraper_broadcast_document_callback)

        # broadcast availability
        self.broadcast_available()
        self.reqchan.start_consuming()

    def stop(self):
        """
        stop() is called to stop consuming on the message bus, and to stop the scraper from running.
        """
        #self.scraper.stop()
        #if self.scraper_thread != None:
        #    self.scraper_thread.stop()
        self.reqchan.stop_consuming()
        self.stopped = True

    def reset_scraper(self):
        """
        resetscraper() calls reset() within the Scraper class.  This resets the state of the scraper.
        This should not be called unless the scraper has been stoped.
        """
        self.scraper.reset()

    def broadcast_available(self):
        """
        broadcastavailable() broadcasts a message to the message bus saying the scraper is available
        to be dispatched a new url to begin scraping.
        """

        # make sure we are not currently scraping
        if self.scraper.status['busy'] == False:

            packet = {
                'available_datetime': str(datetime.datetime.now())
            }
            payload = {
                'command': 'scraper_available',
                'source_id': self.uid,
                'destination_id': 'broadcast',
                'message': packet
            }
            jbody = json.dumps(payload)
            self.respchan.basic_publish(exchange=self.exchange,routing_key='',body=jbody)

        # boadcast our simple status to the bus
        self.broadcast_simple_status()

        #
        # TODO: move this over to it's own timer, no need to do it here.
        #
        #if self.scraper.stopped():
        #    raise Exception("Scraper Wrapper Exiting")
        #else:
        #    threading.Timer(self.interval, self.broadcastavailable).start()
        
        if not self.scraping and not self.stopped:
            threading.Timer(self.interval, self.broadcast_available).start()

    def broadcast_status(self):
        """
        broadcaststatus() broadcasts the status of the scraper to the bus.  This includes all of the information
        kept in all of the state variables within the scraper.  Note: this can be a LOT of information.
        """
        packet = {
            'status': self.scraper.status,
            'url_data': self.status['url_data'],
            'status_datetime': str(datetime.datetime.now())
        }
        payload = {
            'command': 'scraper_status',
            'source_id': self.uid,
            'destination_id': 'broadcast',
            'message': packet
        }
        jbody = json.dumps(payload)
        #time.sleep(.5)
        self.respchan.basic_publish(exchange=self.exchange,routing_key='',body=jbody)

    def broadcast_simple_status(self):
        """
        broadcastsimplestatus() broadcasts a smaller subset of information about the scraper to the bus.  This
        information includes:

            packet = {
                'busy': self.scraper.status['busy'],                         # boolean of busy status
                'link_count': self.scraper.status['linkcount'],               # number of links seen by the scraper
                'link_count': self.scraper.status['link_count'],             # number of links processed by the scraper
                'bad_link_count': len(self.scraper.status['badlinks']),        # number of bad links seen by the scraper
                'target_url': targeturl,                                      # the target url the scraper is working on
                'status_datetime': str(isodatetime)                           # the date/time of the status being sent
            }

        """

        if self.scraper.status['url_data'] == {}:
            targeturl = 'null'
        else:
            targeturl = self.scraper.status['url_data']['target_url']

        packet = {
            'busy': self.scraper.status['busy'],
            'link_count': self.scraper.status['link_count'],
            'link_count': self.scraper.status['link_count'],
            'bad_link_count': len(self.scraper.status['bad_links']),
            'target_url': targeturl,
            'status_datetime': str(datetime.datetime.now())
        }
        payload = {
            'command': 'scraper_status_simple',
            'source_id': self.uid,
            'destination_id': 'broadcast',
            'message': packet
        }
        jbody = json.dumps(payload)
        self.respchan.basic_publish(exchange=self.exchange,routing_key='',body=jbody)

    def scraper_finished_callback(self,payload):
        """
        scraperFinishedCallBack() is the built in, and default, async call back for when the 'scraper finished' command is seen.
        """
        jbody = json.dumps(payload)
        self.respchan.basic_publish(exchange=self.exchange,routing_key='',body=jbody)
        return

    def scraper_started_callback(self,payload):
        """
        scraperFinishedCallBack() is the built in, and default, async call back for when the 'scraper started' command is seen.
        """
        jbody = json.dumps(payload)
        self.respchan.basic_publish(exchange=self.exchange,routing_key='',body=jbody)
        return

    def scraper_broadcast_document_callback(self,payload):
        """
        scraperBroadcastDocCallBack() is the built in, and default, async call back for when the 'scraper finds a new document' command is seen.
        """
        jbody = json.dumps(payload)
        self.respchan.basic_publish(exchange=self.exchange,routing_key='',body=jbody)
        return

    def _scraperstart(self):
        #if self.scraper.start == False:
        #    self.scraper.start()
        #self.scraper.begin()

        self.scraper.find_docs()

    # message handler
    def _reqcallback(self,ch,method,properties,body):
        #try:
        if True:
            response = json.loads(body)
            
            # commented this out because it made the logs almost impossible to read
            
            #if self.DEBUG:
            #    print "Processing Message:\n\t{0}".format(response['command'])
            if response['command'] == 'url_dispatch':
                if response['destination_id'] == self.uid:
                    #print "URL Dispatch Command Seen."
                    #print response
                    if self.scraping == False:
                        #print "[Wrapper] Launching Scraper on URL: '{0}'".format(response['message']['targeturl'])
                        self.scraper.set_url_data(response['message'])
                        #if self.scraper.started == False:
                        #    self.scraper.start()
                        if self.DEBUG:
                            print "Launching scraper thread ..."
                        self.scraping = True
                        self.scraper_thread = threading.Thread(target=self._scraperstart)
                        self.scraper_thread.start()
                        #self._scraperstart()
                        if self.DEBUG:
                            print " ... Scraper launched successfully."

            elif response['command'] == 'scraper_finished':
                if response['source_id'] == self.scraper.uid:
                    self.scraping = False

            elif response['command'] == 'get_status':
                self.broadcaststatus()

            elif response['command'] == 'get_status_simple':
                self.broadcastsimplestatus()

            elif response['command'] == 'reset_scraper':
                if response['destination_id'] == self.uid:
                    self.resetscraper()

            elif response['command'] == 'shutdown':
                if response['destination_id'] == self.uid:
                    print "[{0}] Shutting Down Recieved".format(self.uid)
                    self.stop()

            elif response['command'] == 'global_shutdown':
                print "Global Shutdown Recieved"
                self.stop()

        #except:
        #    if self.DEBUG:
        #        print "Message Error"

if __name__ == '__main__':

    print 'Launching BarkingOwl scraper ...'

    scraper_wrapper = ScraperWrapper(address='localhost',exchange='barkingowl', DEBUG=True)

    try:
        scraper_wrapper.start()
    except:
        #print 'exiting.'
        pass
