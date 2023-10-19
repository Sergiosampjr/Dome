import datetime as dth
import random
import time

from dome.aiengine import AIEngine, Intent
from dome.auxiliary.constants import (OPR_APP_HOME_CMD,
                                      OPR_APP_HOME_WEB,
                                      OPR_APP_TELEGRAM_START,
                                      OPR_ATTRIBUTE_ADD, OPR_ENTITY_ADD)
from dome.config import (ATTRIBUTE_FORMAT, ATTRIBUTE_OK,
                         BYE, CANCEL, CLASS_NOT_IN_DOMAIN, DEBUG_MODE,
                         DELETE_FAILURE, DELETE_SUCCESS, GREETINGS,
                         HELP, MISSING_CLASS, MISUNDERSTANDING,
                         NO_REGISTERS, SAVE_SUCCESS, WEBAPP_HOME_URL, GENERAL_FAILURE, CANCEL_WITHOUT_PENDING_INTENT,
                         CONFIRMATION_WITHOUT_PENDING_INTENT, LIMIT_REGISTERS_MSG, MANAGED_SYSTEM_WEBAPP_BASE_URL,
                         LENGTH_LIMIT_CHARS_TO_SHOW_IN_ROWS, MAX_USER_MSG_SIZE, MAX_USER_MSG_SIZE_MSG, DDoS_MSG)
from dome.domainengine import DomainEngine
from dome.infrastructurecontroller import InterfaceController


class AutonomousController:
    def __init__(self, SE):
        self.__SE = SE  # Security Engine object
        self.__IC = InterfaceController(self)  # Interface Controller object
        self.__DE = DomainEngine(self)  # Domain Engine object
        self.__AIE = AIEngine(self)  # Artificial Intelligence Engine object

    def __monitor(self):
        pass

    def __analyze(self):
        pass

    def plan(self, opr, data):
        # in this version, all tasks are going to be executed immediately
        return self.__execute(opr, data)

    def __execute(self, opr, data):
        # TODO: manager the type of task
        # ...
        if opr == OPR_APP_HOME_WEB:
            self.__IC.update_app_web()
            return {'homeurl': WEBAPP_HOME_URL}
        elif opr == OPR_APP_HOME_CMD:
            self.__IC.getApp_cmd(self.app_chatbot_msg_handler)
            return True  # TODO: to analyse return type/value
        elif opr == OPR_ENTITY_ADD:
            return self.__DE.saveEntity(data['name'])
            # return True #TODO: #3 analysing return type
        elif opr == OPR_ATTRIBUTE_ADD:
            self.__DE.addAttribute(data['entity'], data['name']
                                   , data['type'], data['notnull'])
            self.__IC.update_app_web()
            return True
        elif opr == OPR_APP_TELEGRAM_START:
            self.__IC.update_app_web(True)
            self.__IC.startApp_telegram(self.app_chatbot_msg_handler)
            return True  # TODO: to analyse return type/value
        # else
        return None

    def __knowledge(self):
        pass

    # util methods
    def getEntities(self) -> list:
        return self.__DE.getEntities()

    @staticmethod
    def clear_opr(user_data):
        user_data['previous_intent'] = None
        if 'pending_intent' in user_data:
            user_data['previous_intent'] = user_data['pending_intent']  # saving the previous intent for the tests
        user_data['pending_intent'] = None

        user_data['previous_class'] = None
        if 'pending_class' in user_data:
            user_data['previous_class'] = user_data['pending_class']  # saving the previous class for the tests
        user_data['pending_class'] = None

        user_data['previous_attributes'] = None
        if 'pending_attributes' in user_data:
            # saving the previous class for the tests
            user_data['previous_attributes'] = user_data['pending_attributes']

        user_data['pending_attributes'] = {}

        user_data['previous_where_clause'] = None
        if 'pending_where_clause' in user_data:
            # saving the previous previous_where_clause for the tests
            user_data['previous_where_clause'] = user_data['pending_where_clause']

        user_data['pending_where_clause'] = {}

    def app_chatbot_msg_handler(self, msg, context, dth_income_message):
        is_DDoS = self.__SE.is_DDoS(context._user_id_and_data[0], dth_income_message)
        if is_DDoS:
            return DDoS_MSG
        # else: all ok
        t0 = time.perf_counter()
        if 'id' not in context.user_data:
            # new session
            user_data = self.__SE.create_or_get_user(context._user_id_and_data[0])
            self.clear_opr(user_data)
            context.user_data.update(user_data)

        user_data = context.user_data

        try:
            response = self.app_chatbot_msg_process(msg, user_data=user_data)
        except BaseException as e:
            print('GENERAL_FAILURE', e)
            response = {'user_msg': msg, 'response_msg': GENERAL_FAILURE, 'user_data': user_data, 'error': e}
            self.clear_opr(user_data)

        # logging the message handled
        self.__SE.save_msg_handle_log(msg, user_data['id'], response, time.perf_counter() - t0)

        if DEBUG_MODE:
            return "<b>[DEBUG_MODE_ON]</b>\n" + response['response_msg']
        # else:
        return response['response_msg']

    def __update_model(self, user_data):
        # updating the internal domain model entities and attributes
        domain_entity = self.__DE.saveEntity(user_data['pending_class'])
        for att_name in user_data['pending_attributes'].keys():
            self.__DE.addAttribute(domain_entity, att_name, 'str')
        if 'pending_where_clause' in user_data and user_data['pending_where_clause']:
            for att_name in user_data['pending_where_clause'].keys():
                self.__DE.addAttribute(domain_entity, att_name, 'str')
        try:
            self.__IC.update_app_web()
        except BaseException:
            # rollback the entity and attributes
            self.__DE.init_entities()
            raise Exception('Error updating the model')

    def app_chatbot_msg_process(self, msg, user_data=None):

        return_dict = {'user_msg': msg}

        if ('session_expiration_time' not in user_data
                or user_data['session_expiration_time'] < dth.datetime.now()):
            self.clear_opr(user_data)

        user_data['session_expiration_time'] = dth.datetime.now() + dth.timedelta(minutes=30)
        parser = None
        msg_return_list = MISUNDERSTANDING  # default

        if len(msg) <= MAX_USER_MSG_SIZE:
            parser = self.__AIE.get_msg_parser(msg)

            if parser.intent == Intent.CONFIRMATION:
                if (user_data['pending_intent'] is not None
                        and user_data['pending_class'] is not None
                        and ((len(user_data['pending_attributes']) > 0) or (
                                user_data['pending_intent'] == Intent.READ))):
                    if user_data['pending_intent'] == Intent.ADD:
                        # updating the model
                        self.__update_model(user_data)
                        # add the data
                        self.__DE.add(user_data['pending_class'], user_data['pending_attributes'])
                        msg_return_list = SAVE_SUCCESS
                    elif user_data['pending_intent'] == Intent.UPDATE:
                        # updating the model
                        self.__update_model(user_data)
                        # updating the data
                        self.__DE.update(user_data['pending_class'], user_data['pending_attributes'],
                                         user_data['pending_where_clause'])
                        msg_return_list = SAVE_SUCCESS
                    elif user_data['pending_intent'] == Intent.DELETE:
                        query_result = self.__DE.delete(user_data['pending_class'], user_data['pending_attributes'])
                        if query_result.rowcount == 0:
                            msg_return_list = DELETE_FAILURE
                        else:
                            msg_return_list = DELETE_SUCCESS(query_result.rowcount)
                    elif user_data['pending_intent'] == Intent.READ:
                        query_result = self.__DE.read(user_data['pending_class'], user_data['pending_attributes'])
                        if query_result is None:
                            msg_return_list = NO_REGISTERS
                        else:
                            get_html = ''
                            entity_url = MANAGED_SYSTEM_WEBAPP_BASE_URL + '/' + user_data['pending_class']
                            # iterating over the rows
                            for index, row in query_result.iterrows():
                                str_row = '<a href="' + entity_url + '/' + str(index) + '/">'
                                str_row += user_data['pending_class'].upper() + ' ('
                                str_row += 'id: ' + str(index) + ')'
                                # adding the link to edit the row
                                str_row += '</a>\n'
                                # adding the fields
                                for c in query_result.columns:
                                    if row[c]:
                                        new_row = '<b>' + c.replace('_', ' ').title() + '</b>: ' + str(row[c])
                                        if len(new_row) > LENGTH_LIMIT_CHARS_TO_SHOW_IN_ROWS:
                                            new_row = new_row[:LENGTH_LIMIT_CHARS_TO_SHOW_IN_ROWS] + '...'
                                        str_row += new_row + '\n'
                                get_html += str_row

                            get_html += '------<a href="' + entity_url + '/">View all</a>'
                            get_html += '\n<i>' + LIMIT_REGISTERS_MSG + '</i>'

                            msg_return_list = [get_html]

                    self.clear_opr(user_data)
                else:  # ok without pending intent
                    msg_return_list = CONFIRMATION_WITHOUT_PENDING_INTENT
            elif parser.intent == Intent.CANCELLATION:
                if user_data['pending_intent']:
                    self.clear_opr(user_data)
                    msg_return_list = CANCEL
                else:  # cancel without pending intent
                    msg_return_list = CANCEL_WITHOUT_PENDING_INTENT
            elif parser.intent == Intent.GREETING:
                self.clear_opr(user_data)
                msg_return_list = GREETINGS
            elif parser.intent == Intent.GOODBYE:
                self.clear_opr(user_data)
                msg_return_list = BYE
            elif parser.intent == Intent.HELP:
                self.clear_opr(user_data)
                msg_return_list = HELP
            else:
                if parser.intent == Intent.MEANINGLESS:
                    if user_data['pending_intent'] is not None:  # there is a previous pending operation
                        msg_considered = str(user_data['pending_intent']) + ' '

                        if user_data['pending_class'] is not None:
                            msg_considered += str(user_data['pending_class']) + ' '

                        msg_considered += msg

                        # recursive call with the modified msg
                        return self.app_chatbot_msg_process(msg_considered, user_data=user_data)
                else:  # parse.getIntent() is not None and one of CRUD intents
                    user_data['pending_intent'] = parser.intent
                    if parser.entity_class is None:
                        # use case no indicate class
                        msg_return_list = MISSING_CLASS
                    else:  # all right. one class use case
                        user_data['pending_class'] = parser.entity_class
                        # if is DELETE or READ use case, test if the class is in the domain
                        if ((not self.__DE.entityExists(user_data['pending_class']))
                                and ((user_data['pending_intent'] == Intent.DELETE)
                                     or (user_data['pending_intent'] == Intent.READ))):
                            msg_return_list = CLASS_NOT_IN_DOMAIN(user_data['pending_class'])
                        else:  # class exists
                            # processing the attributes
                            if not parser.attributes:
                                parser.attributes = {}
                            if (user_data['pending_intent'] != Intent.READ) and (len(parser.attributes) == 0):
                                msg_return_list = ATTRIBUTE_FORMAT
                            else:  # all ok!
                                user_data['pending_attributes'] = parser.attributes
                                user_data['pending_where_clause'] = parser.filter_attributes
                                # if is READ use case, call recursively to show results
                                if user_data['pending_intent'] == Intent.READ:
                                    return self.app_chatbot_msg_process('ok', user_data=user_data)
                                # else
                                msg_return_list = ATTRIBUTE_OK(str(user_data['pending_intent']),
                                                               user_data['pending_class'],
                                                               user_data['pending_attributes'],
                                                               user_data['pending_where_clause'])
        else:  # user msg is too long
            # this is an important method to avoid the bot to be blocked by a malicious user
            user_data['user_msg'] = 'MSG_TOO_LONG_DOME'  # to avoid flood the log database with malicious messages
            self.clear_opr(user_data)
            msg_return_list = MAX_USER_MSG_SIZE_MSG

        # updating return_dict
        return_dict['response_msg'] = random.choice(msg_return_list)
        return_dict['user_data'] = user_data
        return_dict['parser'] = parser
        return_dict['debug_info'] = '---debug info:\n[' + msg + ']'

        return return_dict

    def getTransactionDB_path(self):
        return self.__IC.getTransactionDB_path()

    def getWebApp_path(self):
        return self.__IC.getWebApp_path()

    def get_entities_map(self):
        return self.__DE.get_entities_map()

    def get_AIE(self):
        return self.__AIE
