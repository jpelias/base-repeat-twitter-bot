#!/usr/bin/python
# -*- coding: utf-8 -*-

import ConfigParser
import logging
import tweepy
import sqlite3
import os
import time
import sys 

class MyTwitterBot:

    def __init__(self, path):

        self.path = path
        self.logger = logging.getLogger('MyTwitterBot')

        config = ConfigParser.ConfigParser()
        config.read(self.path + "bot_config.ini")

        try:
            self.CONSUMER_KEY = config.get("TwitterAPI", "CONSUMER_KEY")
            self.CONSUMER_SECRET = config.get("TwitterAPI", "CONSUMER_SECRET")
            self.DATABASE = config.get("DBSqlite", "DATABASE_PATH")
            if not os.sep in self.DATABASE:
                self.DATABASE = self.path + self.DATABASE
            self.LOGPATH = config.get("LoggingConf", "LOGFILE_PATH")
            if not os.sep in self.LOGPATH:
                self.LOGPATH = self.path + self.LOGPATH
            self.LOGLEVEL = config.get("LoggingConf", "LOG_LEVEL")
            self.BOTNAME = config.get("RepeatBot", "BOTNAME") 
            self.MESSAGE = config.get("RepeatBot", "MESSAGE") 
            self.KEYWORDS = config.get("RepeatBot", "KEYWORDS")
            self.NOREPLY_ACCOUNTS = config.get("RepeatBot", "NOREPLY_ACCOUNTS").split(',')
            self.NOREPLY_ACCOUNTS.append(self.BOTNAME)
            self.SLEEP_TIME = float(config.get("RepeatBot", "SLEEP_TIME"))

        except ConfigParser.NoOptionError as err:
            print "Non existant entry in the config file: " + err.args[0]
            exit(1)

        except ConfigParser.NoSectionError as err:
            print "Non existant section in the config file: " + err.args[0]
            exit(1) 
        

        self.fhldr_file = logging.FileHandler(self.LOGPATH)
        self.fhldr_file.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(self.fhldr_file)
        self.fhldr_stdout = logging.StreamHandler(sys.__stdout__)
        self.fhldr_stdout.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(self.fhldr_stdout)

        if self.LOGLEVEL == "DEBUG":
            self.logger.setLevel(logging.DEBUG)
        elif self.LOGLEVEL == "INFO":
            self.logger.setLevel(logging.INFO)
        elif self.LOGLEVEL == "WARNING":
            self.logger.setLevel(logging.WARNING)
        elif self.LOGLEVEL == "ERROR":
            self.logger.setLevel(logging.ERROR)
        elif self.LOGLEVEL == "CRITICAL":
            self.logger.setLevel(logging.CRITICAL)

        self.logger.debug("SQLite database checking...")

        if not os.path.isfile(self.DATABASE):
            self.create_database()
        else:
            self.db_handler = sqlite3.connect(self.DATABASE)
            self.db_cursor = self.db_handler.cursor()
        
        self.get_last_credentials()

        self.logger.debug("Getting credentials...")

        if self.token_key == "" or self.token_secret == "":
            self.auth = tweepy.OAuthHandler(self.CONSUMER_KEY, self.CONSUMER_SECRET)
            try:
                self.Authorize()
            except Exception as e:
                self.logger.error("Unauthorized CONSUMER_KEY or CONSUMER_SECRET: " + str(e));
                exit(1)
        else:
            self.auth = tweepy.OAuthHandler(self.CONSUMER_KEY, self.CONSUMER_SECRET)
            self.auth.set_access_token(self.token_key, self.token_secret)

        self.logger.debug("Credentials validation...")

        self.api_handler = tweepy.API(auth_handler = self.auth, secure = True)

        if not self.api_handler.verify_credentials():
            self.Authorize()
            self.api_handler = tweepy.API(self.auth)

        self.logger.debug("Credentials OK !")

        self.logger.info("Bot connected !")
        self.last_search_id = self.get_last_searchresult()


    def create_database(self):
        self.db_handler = sqlite3.connect(self.DATABASE)
        self.db_cursor = self.db_handler.cursor()
        self.db_cursor.execute('''create table credentials(token_key varchar(40), token_secret varchar(40))''')
        self.db_cursor.execute('''create table searchresults (date varchar(50),id int, author_name varchar(20), tweet varchar(140))''')

    def get_last_searchresult(self):
        self.db_cursor.execute('''select id from searchresults order by id desc''')
        res = self.db_cursor.fetchone()
        if res != None:
            return long(res[0])
        else:
            return 0
    
    def save_credentials(self):
        self.db_cursor.execute('''delete from credentials''')
        self.db_cursor.execute('''insert into credentials values(?,?)''', (self.token_key, self.token_secret))
        self.db_handler.commit()

    def get_last_credentials(self):
        self.db_cursor.execute('''select token_key, token_secret from credentials''')
        res = self.db_cursor.fetchone()
        if res != None:
            self.token_key = res[0]
            self.token_secret = res[1]
        else:
            self.token_key = ""
            self.token_secret = ""

    def add_searchresult(self, tweetid, author_name, text):
        self.db_cursor.execute('''insert into searchresults values(?,?,?,?)''', (time.time(), tweetid, author_name, text))
        self.db_handler.commit()

    def Authorize(self):
        auth_url = self.auth.get_authorization_url()
        print 'Access the follwing URL with the bot account: ' + auth_url
        verifier = raw_input('Enter the PIN: ').strip()
        self.auth.get_access_token(verifier)
        self.token_key = self.auth.access_token.key
        self.token_secret = self.auth.access_token.secret
        self.save_credentials()


    def Run(self):
        if self.api_handler.verify_credentials():
            self.logger.info("Waiting for keywords...")
            while True:
                try:
                    search_results = self.api_handler.search(q = self.KEYWORDS, since_id = self.last_search_id)
                except Exception as e:
                    self.logger.error("Error calling Twitter API: " + str(e));
                    continue

                search_results.reverse()
                for search_result in search_results:
                    ignore_tweet = False
                    for account_name in self.NOREPLY_ACCOUNTS:
                        if search_result.from_user.lower() == account_name.lower():
                            self.logger.debug("Ignored tweets from: " + account_name)
                            ignore_tweet = True
                            self.add_searchresult(search_result.id, search_result.from_user,search_result.text)
                            if search_result.id > self.last_search_id:
                                self.last_search_id = search_result.id
                    if ignore_tweet:
                        continue
                    result_text = "@" + search_result.from_user + " " + self.MESSAGE
                    if len(result_text) > 140:
                        continue
                    else:
                        self.logger.info("Sending tweet to @" + search_result.from_user)
                        try:
                            if search_result.id > self.last_search_id:
                                self.last_search_id = search_result.id
                                self.add_searchresult(search_result.id, search_result.from_user,search_result.text)
                                self.api_handler.update_status(status = result_text, in_reply_to_status_id = search_result.id)
                        except Exception as e:
                            self.logger.error("Error calling Twitter API: " + str(e));
                            continue

                time.sleep(self.SLEEP_TIME)
                
        else:
            self.logger.error("Authentication failure !")

    def Quit(self):
        self.logger.info("Diconnecting...")
        self.db_handler.close()
        self.logger.info("Bot disconnected !")
        self.fhldr_file.flush()
        self.fhldr_file.close()
        self.fhldr_stdout.flush()
        self.fhldr_stdout.close()

if __name__ == "__main__":
    path = os.path.dirname(os.path.abspath(__file__))
    bot = MyTwitterBot(path +  os.sep)
    try:
        bot.Run()
    except (KeyboardInterrupt, SystemExit):
        bot.Quit()
