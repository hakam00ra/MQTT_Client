import configparser
import csv
import io
import json
import os
import random
import sqlite3
import sys
import cv2 as cv
import folium
import numpy as np
import paho.mqtt.client as mqtt
import polyline
import requests
from datetime import datetime
from PyQt5 import QtGui
from PyQt5.QtCore import QObject, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QImage, QTextCursor
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (QAction, QApplication, QCheckBox, QComboBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMainWindow, QMenu, QMessageBox,
                             QPushButton, QSizePolicy, QTableWidget,
                             QTableWidgetItem, QTabWidget, QTextEdit,
                             QVBoxLayout, QWidget)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def initialize_database():
    conn = sqlite3.connect('newDatabase26.db')
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS data (
        id INTEGER PRIMARY KEY,
        topic TEXT,
        message TEXT,
        timestamp TEXT,                   
        imei TEXT
    )
    ''')    
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY,
        topic TEXT,
        message TEXT,
        timestamp TEXT,                   
        imei TEXT
    )
    ''')
    # TODO change to match previous tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY,
        imei TEXT,
        read_topic TEXT,                   
        comments TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create an index on the 'topic' column for efficient message retrieval
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_topic ON data(topic)')

    # Create an index on the 'imei' column for efficient device retrieval
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_imei ON data(imei)')

    conn.commit()
    conn.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("MQTT Client and Database")
        self.setWindowIcon(QtGui.QIcon(resource_path("infinite.ico")))
        self.setGeometry(100, 100, 400, 300)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout(self.central_widget)

        self.tab_widget = QTabWidget(self)
        self.layout.addWidget(self.tab_widget)

        # Create and add multiple pages as tabs
        self.page1 = Page1()
        self.page2 = Page2()
        self.page3 = Page3()
        self.page4 = Page4()

        self.page2.device_change.connect(self.page4.populate_combo_box)

        self.tab_widget.addTab(self.page1, "MQTT Client")
        self.tab_widget.addTab(self.page2, "Devices")
        self.tab_widget.addTab(self.page3, "SQLite Database")
        self.tab_widget.addTab(self.page4, "GPS Data")
        self.showMaximized()

class Pages(QWidget):
    device_change = pyqtSignal(int)
    def __init__(self):
        super().__init__()  


class Page1(Pages):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Create a QTabWidget for the sub-tabs within the "Broker" tab
        sub_tab_widget = QTabWidget(self)

        # Create sub-tabs and add them to the sub_tab_widget        
        connectTab = SubTab1()
        publishTab = SubTab2()
        subscribeTab = SubTab3()
        connectTab.clientReady.connect(subscribeTab.onClientReady)
        connectTab.clientReady.connect(publishTab.onClientReady)
        connectTab.signals.connected.connect(subscribeTab.showButton)
        connectTab.signals.connected.connect(publishTab.showButton)
        
        sub_tab_widget.addTab(connectTab, "Connect")
        sub_tab_widget.addTab(publishTab, "Publish")
        sub_tab_widget.addTab(subscribeTab, "Subscribe")

        # Add the sub-tab widget to the main layout
        self.layout.addWidget(sub_tab_widget)

class Subs(QWidget):
    clientReady = pyqtSignal(mqtt.Client)
    def __init__(self):
        super().__init__()  
        self.sharedClientID = None

class SubTab1(Subs):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.signals = WorkerSignals()

        # Create a form layout for organizing label and QLineEdit pairs
        form_layout = QFormLayout()
        self.client = None  # Initialize client as None
        
        subscribedTopics = QLabel("Brokers:")
        form_layout.addWidget(subscribedTopics)
        # Create a QTableWidget to display the list of topics        
        self.tableWidget = QTableWidget(self)
        self.tableWidget.setColumnCount(1)  # Two columns: Topic and Subscription Status
        self.tableWidget.setHorizontalHeaderLabels(['Name'])
        form_layout.addWidget(self.tableWidget)

        # Connect the context menu to the table widget
        self.tableWidget.setContextMenuPolicy(3)  # 3 is for Qt.CustomContextMenu
        #self.tableWidget.customContextMenuRequested.connect(self.show_context_menu)
        
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Broker")
        self.remove_button = QPushButton("Delete Broker")
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        self.add_button.clicked.connect(self.add_broker)
        self.remove_button.clicked.connect(self.remove_broker)
        self.layout.addLayout(button_layout)
        
        self.save_button = QPushButton("Save")        
        self.save_button.clicked.connect(self.save_mqtt_parameters)
        form_layout.addRow(self.save_button)            

        broker_label = QLabel("Broker Address:")
        self.ip_edit = QLineEdit()
        self.ip_edit.setMaximumWidth(200)  # Set a maximum width
        form_layout.addRow(broker_label, self.ip_edit)

        port_label = QLabel("Port:")
        self.port_edit = QLineEdit()
        self.port_edit.setMaximumWidth(80)  # Set a maximum width
        form_layout.addRow(port_label, self.port_edit)

        username_label = QLabel("Username:")
        self.username_edit = QLineEdit()
        self.username_edit.setMaximumWidth(200)  # Set a maximum width
        form_layout.addRow(username_label, self.username_edit)

        password_label = QLabel("Password:")
        self.password_edit = QLineEdit()
        self.password_edit.setMaximumWidth(200)  # Set a maximum width
        form_layout.addRow(password_label, self.password_edit)

        client_label = QLabel("Client ID:")
        self.client_edit = QLineEdit()
        self.client_edit.setMaximumWidth(200)  # Set a maximum width
        form_layout.addRow(client_label, self.client_edit)

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_to_broker)    
        form_layout.addRow(self.connect_button)           

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self.disconnect_from_broker)
        form_layout.addRow(self.disconnect_button)
        self.disconnect_button.hide()

        self.tableWidget.itemClicked.connect(self.load_mqtt_parameters)
        self.signals.connected.connect(self.show_success_message)
        # Add the form layout to the sub-tab layout
        self.layout.addLayout(form_layout)
        self.load_brokers()

    def add_broker(self):
        # Add a new row with empty cells for IMEI and comments
        row_position = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row_position)
        self.tableWidget.setItem(row_position, 0, QTableWidgetItem(""))
        
    def remove_broker(self):
        # Remove the selected row(s)
        config = configparser.ConfigParser()
        config.read("config.ini")
        selected_rows = set(index.row() for index in self.tableWidget.selectionModel().selectedRows())
        for row in reversed(sorted(selected_rows)):
            broker_item = self.tableWidget.item(row, 0)
            broker = broker_item.text() if broker_item else ""
            brokerNames_config = config["Brokers"]
            for key, value in brokerNames_config.items():
                if value == broker:
                    del brokerNames_config[key]
            
            if f"{broker}" in config:
                # Remove the section 'MQTT' and its contents
                config.remove_section(f"{broker}")

            self.tableWidget.removeRow(row)
        with open("config.ini", "w") as configfile:
            config.write(configfile)        

    def save_mqtt_parameters(self):
        selected_rows = set(index.row() for index in self.tableWidget.selectionModel().selectedRows())
        for row in (sorted(selected_rows)):
            broker_item = self.tableWidget.item(row, 0)
            broker = broker_item.text() if broker_item else ""

            config = configparser.ConfigParser()
            config.read("config.ini")

            if "Brokers" not in config:
                config["Brokers"] = {}

            brokerName_config = config["Brokers"]

            #topic_key = f"Topic {len(topics_config) + 1}"        
            topic_key = broker
            brokerName_config[topic_key] = broker
            
            if f"{broker}" not in config:
                config[f"{broker}"] = {}

            brokers_config = config[f"{broker}"]
            
            brokers_config["broker"] = self.ip_edit.text()
            brokers_config["port"] = self.port_edit.text()
            brokers_config["username"] = self.username_edit.text()
            brokers_config["password"] = self.password_edit.text()
            brokers_config["client_id"] = self.client_edit.text()
            with open("config.ini", "w") as configfile:
                config.write(configfile)

    def load_brokers(self):
        config = configparser.ConfigParser()
        config.read("config.ini")
        if "Brokers" in config:
            brokerNames_config = config["Brokers"]
            for key in brokerNames_config: 
                broker = brokerNames_config[key]
                #topics.append(topic)
                row_position = self.tableWidget.rowCount()
                self.tableWidget.insertRow(row_position)
                self.tableWidget.setItem(row_position, 0, QTableWidgetItem(broker))                
                #self.topic_edit.clear()

    def load_mqtt_parameters(self):
        config = configparser.ConfigParser()
        config.read("config.ini")
        selected_rows = set(index.row() for index in self.tableWidget.selectionModel().selectedRows())       
        for row in (sorted(selected_rows)):
            broker_item = self.tableWidget.item(row, 0)
            broker = broker_item.text() if broker_item else ""
        
            if f"{broker}" in config:
                mqtt_config = config[f"{broker}"]
                self.ip_edit.setText(mqtt_config.get("broker", ""))
                self.port_edit.setText(mqtt_config.get("port", ""))
                self.username_edit.setText(mqtt_config.get("username", ""))
                self.password_edit.setText(mqtt_config.get("password", ""))
                self.client_edit.setText(mqtt_config.get("client_id", ""))
        
    def disconnect_from_broker(self):
        self.client.disconnect()

    def connect_to_broker(self):
        # Get MQTT broker settings from the QLineEdit widgets
        broker = self.ip_edit.text()
        port_str = self.port_edit.text()
        username = self.username_edit.text()
        password = self.password_edit.text()
        client_id = self.client_edit.text()

         # Validate the port number
        if not port_str.isdigit():
            QMessageBox.critical(self, "Invalid Port", "Please enter a valid port number.", QMessageBox.Ok)
            return

        port = int(port_str)
        self.connect_mqtt_broker(broker=broker, port=port, username=username, password=password, client_id=client_id)

    def connect_mqtt_broker(self, broker, port, username, password, client_id):
        try:
            # Create an MQTT client instance
            self.client = mqtt.Client(client_id=client_id)

            # Set username and password if provided
            if username:
                self.client.username_pw_set(username, password)

            self.client.connect(broker, port)
            self.sharedClientID = self.client
            self.clientReady.emit(self.sharedClientID)  # Emit a signal when the client is ready
            self.client.on_disconnect = self.on_disconnect  # Set the on_disconnect event handler
            self.client.on_connect = self.on_connect
            self.client.loop_start()

        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Failed to connect to MQTT broker. Error: {str(e)}", QMessageBox.Ok)

    def show_success_message(self, connected):
        if connected==1:
            #self.paintEvent(1)
            self.connect_button.hide()
            self.disconnect_button.show()
            QMessageBox.information(self, "Connection Status", "Connected to MQTT broker successfully.", QMessageBox.Ok)
        else:
            #self.paintEvent(0)
            self.connect_button.show()
            self.disconnect_button.hide()
            QMessageBox.information(self, "Connection Status", "Disconnected from MQTT broker successfully.", QMessageBox.Ok)
    
    def on_disconnect(self, client, userdata, rc):
        self.signals.connected.emit(0)
    
    def on_connect(self, client, userdata, flags, rc):
        self.signals.connected.emit(1)

class SubTab2(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.signals = WorkerSignals()

        # Create a form layout for organizing label, QLineEdit, QTextEdit, and QPushButton
        form_layout = QFormLayout()

        # Add a label for the topic entry
        topic_label = QLabel("Topic:")
        self.topic_edit = QLineEdit()
        self.topic_edit.setPlaceholderText("Enter a topic")
        form_layout.addRow(topic_label, self.topic_edit)

        # Add a label for the message entry
        message_label = QLabel("Message:")
        self.message_edit = QTextEdit()
        self.message_edit.setPlaceholderText("Enter your message")
        form_layout.addRow(message_label, self.message_edit)

        # Add a checkbox for the retain flag
        self.retain_checkbox = QCheckBox("Retain")
        form_layout.addRow(self.retain_checkbox)

        # Add a button to publish the message
        self.publish_button = QPushButton("Publish")
        self.publish_button.clicked.connect(self.publish_message)
        form_layout.addRow(self.publish_button)
        self.signals.connected.connect(self.showButton)
        self.publish_button.hide()
        self.layout.addLayout(form_layout)

    def publish_message(self):
        topic = self.topic_edit.text()
        message = self.message_edit.toPlainText()
        retain = self.retain_checkbox.isChecked()

        if topic and message:
            # Publish the message to the MQTT topic
            self.sharedClientID.publish(topic, message, retain=retain)
            """
            QMessageBox.information(
                self, "Publish Status", f"Published to topic '{topic}' with retain={retain}.", QMessageBox.Ok
            )
            """

    def onClientReady(self, client):
        self.sharedClientID = client
    
    def showButton(self, show):
        if show == 0:
            self.publish_button.hide()
        else:
            self.publish_button.show()

class SubTab3(Subs):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.signals = WorkerSignals()

        # Create a form layout for organizing label and QTextEdit pairs
        form_layout = QVBoxLayout()
        self.messageCounter = 0
        # Add a label for the topic entry
        topics_label = QLabel("Enter a topic:")
        form_layout.addWidget(topics_label)

        # Add a QTextEdit for entering MQTT topics
        self.topic_edit = QTextEdit()
        self.topic_edit.setPlaceholderText("Enter a topic and press 'Add Topic'")
        self.topic_edit.setMaximumHeight(100)
        form_layout.addWidget(self.topic_edit)

        # Add a button to add the topic to the table
        add_topic_button = QPushButton("Add Topic")
        add_topic_button.clicked.connect(self.add_topic)
        form_layout.addWidget(add_topic_button)

        subscribedTopics = QLabel("Topics:")
        form_layout.addWidget(subscribedTopics)
        # Create a QTableWidget to display the list of topics
        self.topic_table_widget = QTableWidget()
        self.topic_table_widget.setColumnCount(2)  # Two columns: Topic and Subscription Status
        self.topic_table_widget.setHorizontalHeaderLabels(['Topic', 'Subscribed'])
        self.topic_table_widget.setMaximumHeight(200)
        form_layout.addWidget(self.topic_table_widget)

        # Add a button to subscribe/unsubscribe to/from the selected topic
        self.subscribe_button = QPushButton("Subscribe/Unsubscribe")
        self.subscribe_button.clicked.connect(self.subscribe_to_topic)
        form_layout.addWidget(self.subscribe_button)
        self.subscribe_button.hide()
        subscribedTopics = QLabel("Messages:")
        form_layout.addWidget(subscribedTopics)
        
        self.layout.addLayout(form_layout)

        # Create a context menu (to delete topics)
        self.context_menu = QMenu(self)
        delete_action = QAction("Delete", self)
        delete_action.triggered.connect(self.delete_topic)
        self.context_menu.addAction(delete_action)

        # Connect the context menu to the table widget
        self.topic_table_widget.setContextMenuPolicy(3)  # 3 is for Qt.CustomContextMenu
        self.topic_table_widget.customContextMenuRequested.connect(self.show_context_menu)


        # Create a separate area to display incoming messages for subscribed topics        
        self.message_display = QTextEdit()
        self.message_display.setReadOnly(True)  # Make it read-only
        self.message_display.setMinimumSize(300, 550)
        self.layout.addWidget(self.message_display)

        self.signals.connected.connect(self.showButton)
        self.load_topicConfig()

    def show_context_menu(self, pos):
        # Show the context menu at the cursor position
        self.context_menu.exec_(self.topic_table_widget.mapToGlobal(pos))

    def delete_topic(self):
        selected_items = self.topic_table_widget.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            deleted_topic_item = self.topic_table_widget.item(row, 0)  # Get the topic item in the first column
            deleted_topic = deleted_topic_item.text()
            #print(deleted_topic)
            self.delete_topicConfig(deleted_topic)
            self.topic_table_widget.removeRow(row)           

    def add_topic(self):
        topic = self.topic_edit.toPlainText().strip()
        if topic:
            row_position = self.topic_table_widget.rowCount()
            self.topic_table_widget.insertRow(row_position)
            self.topic_table_widget.setItem(row_position, 0, QTableWidgetItem(topic))
            self.topic_table_widget.setItem(row_position, 1, QTableWidgetItem("No"))
            self.topic_edit.clear()

            self.save_topicConfig(topic)

    def save_topicConfig(self, topic):
        config = configparser.ConfigParser()
        config.read("config.ini")
        if "Topics" not in config:
            config["Topics"] = {}

        topics_config = config["Topics"]

        #topic_key = f"Topic {len(topics_config) + 1}"        
        topic_key = topic
        topics_config[topic_key] = topic

        with open("config.ini", "w") as configfile:
            config.write(configfile)

    def delete_topicConfig(self, topic):
        config = configparser.ConfigParser()
        config.read("config.ini")
        topics_config = config["Topics"]
        for key, value in topics_config.items():
            if value == topic:
                del topics_config[key]
        with open("config.ini", "w") as configfile:
            config.write(configfile)

    def load_topicConfig(self):
        config = configparser.ConfigParser()
        config.read("config.ini")
        #topics = []
        if "Topics" in config:
            topics_config = config["Topics"]
            for key in topics_config: 
                topic = topics_config[key]
                #topics.append(topic)
                row_position = self.topic_table_widget.rowCount()
                self.topic_table_widget.insertRow(row_position)
                self.topic_table_widget.setItem(row_position, 0, QTableWidgetItem(topic))
                self.topic_table_widget.setItem(row_position, 1, QTableWidgetItem("No"))
                self.topic_edit.clear()
            #print(topics)

    def subscribe_to_topic(self):
        selected_row = self.topic_table_widget.currentRow()
        if selected_row != -1:
            topic_item = self.topic_table_widget.item(selected_row, 0)
            self.status_item = self.topic_table_widget.item(selected_row, 1)

            if self.status_item.text() == "No":
                # Subscribe to the MQTT topic
                topic = topic_item.text()
                self.sharedClientID.subscribe(topic)
                self.status_item.setText("Yes")
                """
                QMessageBox.information(
                    self, "Subscription Status", f"Subscribed to topic '{topic}'.", QMessageBox.Ok
                )
                """
            else:
                # Unsubscribe from the MQTT topic
                topic = topic_item.text()
                self.sharedClientID.unsubscribe(topic)
                self.status_item.setText("No")
                """
                QMessageBox.information(
                    self, "Subscription Status", f"Unsubscribed from topic '{topic}'.", QMessageBox.Ok
                )
                """

    def onClientReady(self, client):
        self.sharedClientID = client
        self.sharedClientID.on_message = self.on_message_received  # Set the message handler

    def showButton(self, show):
        if show == 0:
            num_rows = self.topic_table_widget.rowCount()
            for row in range(num_rows):
                item = self.topic_table_widget.item(row, 1)
                item.setText("No")
            
            self.subscribe_button.hide()
        else:
            self.subscribe_button.show()

    def on_message_received(self, client, userdata, message):
        #client_id = client._client_id
        
        self.messageCounter += 1
        topic = message.topic
        # Silly way to make out if the message contains an image
        if len(message.payload)>2000:
            payload = message.payload.hex()
            print(payload)
        else:
            try:
                payload = message.payload.decode("utf-8")
            except ValueError as e:
                print(f"Error: {e}")
                return
        message_text = f"#{self.messageCounter}\nTopic: {topic}\nMessage:\n{payload}\n\n"
        if len(message.payload)>2000:
            self.handle_image(payload, topic)
        else:
            self.message_display.append(message_text)

        cursor = self.message_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.message_display.setTextCursor(cursor)       
        self.insert_telemetry_data(payload, topic)     
    
    def handle_image(self, payload, topic):
        print(payload)
        try:
            image_bytes = bytes.fromhex(payload)
        except ValueError as e:
            print(f"Error: {e}")
            return
        image = QImage()
        image.loadFromData(image_bytes)             
        image_size = cv.imdecode(np.frombuffer(image_bytes, np.uint8), cv.IMREAD_COLOR)
        desired_height, desired_width, channels = image_size.shape
        if desired_height > 350:
            desired_height = 350
        if desired_width > 400:
            desired_width = 400
        scaled_image = image.scaled(desired_width, desired_height, aspectRatioMode=Qt.KeepAspectRatio)
        cursor = QTextCursor(self.message_display.document())
        cursor.movePosition(QTextCursor.End)
        self.message_display.setTextCursor(cursor)
        
        cursor.insertText(f"#{self.messageCounter}\nTopic: {topic}\nImage: \n\n")
        cursor.insertImage(scaled_image)

    def insert_telemetry_data(self, payload, topic):  
        data_lines = payload.strip().split('\n')
        imei = data_lines[0].strip()
        save = 0

        for sublist in devicesRAM:
            if sublist[0]==imei or sublist[1]==topic:
                save = 1
                conn = sqlite3.connect('newDatabase26.db')
                cursor = conn.cursor()  
                current_timestamp = datetime.now()            
                formatted_timestamp = current_timestamp.strftime("%Y-%m-%d %H:%M:%S")                            

        for sublist in devicesRAM:
            if sublist[0]==imei:                                            
                for line in data_lines[1:]:
                    line = line.strip()
                    parts = line.strip().split(',')
                    timestamp = parts[0]
                    
                    cursor.execute('''
                        INSERT INTO data (imei, timestamp, message, topic)
                        VALUES (?, ?, ?, ?)
                    ''', (imei, timestamp, line, topic))        

        # Check if topic is a read topic for the registered devices
        for sublist in devicesRAM:
            if sublist[1]==topic:                
                cursor.execute('''
                    INSERT INTO commands (imei, timestamp, message, topic)
                    VALUES (?, ?, ?, ?)
                ''', (sublist[0], formatted_timestamp, payload.strip(), topic))
        if save==1:            
            conn.commit()
            conn.close()    
        
        
class Page2(Pages):
    def __init__(self):
        super().__init__()        
        self.layout = QVBoxLayout(self)

        # Create a QTableWidget for displaying devices
        self.tableWidget = QTableWidget(self)
        self.tableWidget.setColumnCount(3)  # Two columns: IMEI and Comments
        self.tableWidget.setHorizontalHeaderLabels(['IMEI', 'Read Topic', 'Comments'])
        self.layout.addWidget(self.tableWidget)

        # Create buttons for adding and removing devices
        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Device")
        self.remove_button = QPushButton("Remove Device")
        self.add_to_db = QPushButton("Add to Database")
        self.del_from_db = QPushButton("Delete from Database")
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addWidget(self.add_to_db)
        button_layout.addWidget(self.del_from_db)
        self.layout.addLayout(button_layout)

        # Connect button signals to functions
        self.add_button.clicked.connect(self.add_device)
        self.remove_button.clicked.connect(self.remove_device)
        self.add_to_db.clicked.connect(self.insert_deviceSQL)
        self.del_from_db.clicked.connect(self.delete_deviceSQL)
        
        self.load_devicesSQL()

    def add_device(self):
        # Add a new row with empty cells for IMEI and comments
        row_position = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row_position)
        self.tableWidget.setItem(row_position, 0, QTableWidgetItem(""))
        self.tableWidget.setItem(row_position, 1, QTableWidgetItem(""))               

    def remove_device(self):
        # Remove the selected row(s)
        selected_rows = set(index.row() for index in self.tableWidget.selectionModel().selectedRows())
        for row in reversed(sorted(selected_rows)):
            self.tableWidget.removeRow(row)

    def load_devicesSQL(self):
        global devicesRAM
        conn = sqlite3.connect('newDatabase26.db')
        cursor = conn.cursor()

        # Retrieve devices from the 'data' table where 'type' is 'device'
        cursor.execute('SELECT imei, read_topic, comments FROM devices')
        devices = cursor.fetchall()

        conn.close()

        # Populate the QTableWidget with the retrieved devices
        self.tableWidget.setRowCount(len(devices))
        for row, (imei, read_topic, comments) in enumerate(devices):
            self.tableWidget.setItem(row, 0, QTableWidgetItem(imei))
            self.tableWidget.setItem(row, 1, QTableWidgetItem(read_topic))
            self.tableWidget.setItem(row, 2, QTableWidgetItem(comments))
            devicesRAM.append([imei, read_topic, comments])
            
    def insert_deviceSQL(self):        
        conn = sqlite3.connect('newDatabase26.db')
        cursor = conn.cursor()
        current_timestamp = datetime.now()            
        formatted_timestamp = current_timestamp.strftime("%Y-%m-%d %H:%M:%S")

        selected_rows = set(index.row() for index in self.tableWidget.selectionModel().selectedRows())
        for row in (sorted(selected_rows)):
            # Retrieve the IMEI and comments from the new row
            imei_item = self.tableWidget.item(row, 0)
            read_topic_item = self.tableWidget.item(row, 1)
            comments_item = self.tableWidget.item(row, 2)
            
            imei = imei_item.text() if imei_item else ""
            read_topic = read_topic_item.text() if read_topic_item else ""
            comments = comments_item.text() if comments_item else ""
            duplicate = 0
            for device in devicesRAM:
                if device[0]==imei:
                    duplicate = 1
            if duplicate:
                QMessageBox.warning(self, "Database error", "Device already exists in database.", QMessageBox.Ok)
            else:
                # Insert the device information into the SQLite database
                cursor.execute('''
                    INSERT INTO devices (imei, read_topic, comments, timestamp) VALUES (?, ?, ?, ?)
                ''', (imei, read_topic, comments, formatted_timestamp))
                devicesRAM.append([imei, read_topic, comments]) 

        conn.commit()
        conn.close()
               
        self.device_change.emit(1)
        
    def delete_deviceSQL(self):
        global devicesRAM
        conn = sqlite3.connect('newDatabase26.db')
        cursor = conn.cursor()

        selected_rows = set(index.row() for index in self.tableWidget.selectionModel().selectedRows())
        for row in sorted(selected_rows, reverse=True):
            # Retrieve the IMEI from the selected row
            imei_item = self.tableWidget.item(row, 0)
            imei = imei_item.text() if imei_item else ""

            # Delete the device from the SQLite newDatabase26 based on 'type' and 'imei'
            cursor.execute('DELETE FROM devices WHERE imei = ?', (imei,))
            devicesRAM = [sub_list for sub_list in devicesRAM if sub_list[0] != imei]
            self.tableWidget.removeRow(row)
        conn.commit()
        conn.close()        
       
        self.device_change.emit(1)
        

class Page3(Pages):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        
        search_criteria_layout = QHBoxLayout()
        self.label = QLabel("Search based on:", self)
        search_criteria_layout.addWidget(self.label)

        self.search_criteria_combo = QComboBox()
        self.search_criteria_combo.addItem("IMEI")
        self.search_criteria_combo.addItem("Topic")
        search_criteria_layout.addWidget(self.search_criteria_combo)
        
        self.layout.addLayout(search_criteria_layout)

        self.search_input_edit = QLineEdit()
        self.query_button = QPushButton("Query Database")        
        self.layout.addWidget(self.search_input_edit)
        self.layout.addWidget(self.query_button)
        
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(5)  # Adjust the number of columns as needed
        self.layout.addWidget(self.table_widget)

        self.download_button = QPushButton("Download Data")  # Add this button
        self.layout.addWidget(self.download_button)

        table_size_policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table_widget.setSizePolicy(table_size_policy)

        self.query_button.clicked.connect(self.query_database)
        self.download_button.clicked.connect(self.download_data)

    def query_database(self):
        search_criteria = self.search_criteria_combo.currentText()

        search_input = self.search_input_edit.text()

        self.table_widget.clear()
        self.table_widget.setRowCount(0)
        self.table_widget.setColumnCount(4)  # Adjust the number of columns as needed
        self.table_widget.setHorizontalHeaderLabels(['IMEI', 'Timestamp', 'Message', 'Topic'])

        conn = sqlite3.connect('newDatabase26.db')
        cursor = conn.cursor()

        cursor.execute(f'SELECT imei, timestamp, message, topic FROM data WHERE {search_criteria} = ?', (search_input,))

        data = cursor.fetchall()
        if len(data)==0 and search_criteria=='Topic':            
            cursor.execute(f'SELECT imei, timestamp, message, topic FROM commands WHERE topic = ?', (search_input,))
            data = cursor.fetchall()
        conn.close()

        self.table_widget.setRowCount(len(data))
        for row, (imei, timestamp, message, topic) in enumerate(data):
            self.table_widget.setItem(row, 0, QTableWidgetItem(imei))
            self.table_widget.setItem(row, 1, QTableWidgetItem(timestamp))
            self.table_widget.setItem(row, 2, QTableWidgetItem(message))
            self.table_widget.setItem(row, 3, QTableWidgetItem(topic))        

    def download_data(self):
        search_criteria = self.search_criteria_combo.currentText()

        search_input = self.search_input_edit.text()

        if search_input:
            options = QFileDialog.Options()
            options |= QFileDialog.ReadOnly
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Data", "", "CSV Files (*.csv);;All Files (*)", options=options)

            if file_path:
                conn = sqlite3.connect('newDatabase26.db')
                cursor = conn.cursor()

                cursor.execute(f'SELECT imei, timestamp, message, topic FROM data WHERE {search_criteria} = ?', (search_input,))
                data = cursor.fetchall()

                conn.close()

                if data:
                    with open(file_path, 'w', newline='') as csv_file:
                        csv_writer = csv.writer(csv_file)
                        csv_writer.writerow(["IMEI", "Timestamp", "Message", "Topic"])  # CSV header
                        csv_writer.writerows(data)

                    QMessageBox.information(self, "Download Status", "Data downloaded successfully.", QMessageBox.Ok)
                else:
                    QMessageBox.warning(self, "No Data", f"No data found for the specified {search_criteria}.", QMessageBox.Ok)
            else:
                QMessageBox.warning(self, "File Not Selected", "Please choose a file location to save the data.", QMessageBox.Ok)


class Page4(Pages):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        
        self.map = QWebEngineView()
        self.layout.addWidget(self.map)
        min_lat, max_lat = 40.4774, 45.01585  # Latitude boundaries
        min_lon, max_lon = -74.2591, -73.7004  # Longitude boundaries

        initial_latitude = random.uniform(min_lat, max_lat)
        initial_longitude = random.uniform(min_lon, max_lon)
        map_url = QUrl(f"https://www.openstreetmap.org/?mlat={initial_latitude}&mlon={initial_longitude}#map=13/{initial_latitude}/{initial_longitude}")
        self.map.setUrl(map_url)
        
        search_criteria_layout = QHBoxLayout()
        self.label = QLabel("Retrieve GPS data for device with IMEI:", self)
        search_criteria_layout.addWidget(self.label)

        self.search_criteria_combo = QComboBox()       
        search_criteria_layout.addWidget(self.search_criteria_combo)
                
        self.layout.addLayout(search_criteria_layout)
        self.populate_combo_box()

        self.map_button = QPushButton("Map GPS data")
        self.layout.addWidget(self.map_button)
        self.map_button.clicked.connect(self.map_data)

    def populate_combo_box(self):
        self.search_criteria_combo.clear()        
        for device in devicesRAM:            
            self.search_criteria_combo.addItem(f'{device[0]} ({device[2]})')
        
    def map_data(self):
        device = self.search_criteria_combo.currentText().split(' ')[0]        
        conn = sqlite3.connect('newDatabase26.db')
        cursor = conn.cursor()                 
        cursor.execute(f'SELECT imei, timestamp, message, topic FROM commands WHERE imei= ?', (device,))
        data = cursor.fetchall()
        conn.close()
        coordinates = []
        gpsData = 0        
        for line in data:            
            if (',+' in line[2] or ',-' in line[2]) and ',-,-' not in line[2]:
                fix, lat, lon = line[2].split(',')
                coordinates.append((float(lat), float(lon)))  
                gpsData = 1

        if gpsData==1:
            self.map_route(coordinates, device)
        else:
            QMessageBox.critical(self, "GPS Map", "No GPS data available for this device.", QMessageBox.Ok)
                
    def map_route(self, coordinates, device):
        map = folium.Map(location=coordinates[0], zoom_start=13)
        
        if len(coordinates)>1:
            route = self.get_route(coordinates)[0]
            result = self.get_route(coordinates)[1]
        
            folium.PolyLine(route, color="red", weight=2.5, opacity=1, dash_array='10').add_to(map)
            coordCounter = 0
            for index, coord in enumerate(coordinates):                    
                color = 'blue'
                if (index==0):
                    color = 'green'
                elif (index==len(coordinates)-1):
                    color = 'black'
                d2d = result['routes'][0]['legs'][index-1]['distance']
                coordCounter += 1
                if (index==0):
                    d2d = 0
                    folium.Marker(location = coord, popup="Start\n<i>%s</i>\nd2d: %.1fm" %(coord, d2d),  icon=folium.Icon(color=color)).add_to(map)
                else:            
                    folium.Marker(location = coord, popup="%d\n<i>%s</i>\nd2d: %.1fm" %(coordCounter-1, coord, d2d),  icon=folium.Icon(color=color)).add_to(map)
                #custom_icon = folium.DivIcon(
                #    html=f'<div style="font-weight: bold; font-size: 16px;"><i class="fa fa-map-marker fa-2x" style="color: {color};"></i><br>{counter}</div>',
                #    icon_size=(60, 60)  # Adjust the icon size as needed
                #)

            # folium.Marker(
            #     location=coord,
            #     popup="<i>%s</i>\nd2d: %.1fm" %(coord, d2d),
            #     icon=custom_icon
            # ).add_to(map)                
                if (index==len(coordinates)-1):
                    folium.Marker(location = coord, popup="End\n<i>%s</i>\nd2d: %.1fm\nTotal: %.1fm" %(coord, d2d, result['routes'][0]['distance']),  icon=folium.Icon(color=color)).add_to(map)                    
        else:            
            folium.Marker(location=coordinates[0], popup="Start\n<i>%s</i>\nd2d: 0m" % (coordinates[0],), icon=folium.Icon(color='blue')).add_to(map)

        map.save(f"{device}_map.html")       
        self.map.setHtml(open(f'{device}_map.html').read())
        self.map.show()
        return map 
        
    def get_route(self, coordinates):
        coords = ";".join(f"{coord[1]},{coord[0]}" for coord in coordinates)
        url = f"https://router.project-osrm.org/route/v1/driving/{coords}"
        response = requests.get(url)
        res = response.json()
        poly = polyline.decode(res['routes'][0]['geometry'])
        
        if response.status_code == 200:
            data = json.loads(response.text)
        else:
            print(f"Request failed with status code: {response.status_code}")
            return []
        
        """ This calculates the total trigonometric distance and not driving distance, driving distance is inside the url responce
        total_distance = 0
        for i in range(len(poly) - 1):
            coord1 = poly[i]
            coord2 = poly[i + 1]
            total_distance += geopy.distance.distance(coord1, coord2).km
        """
        return poly, res



class WorkerSignals(QObject):
    connected = pyqtSignal(int)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    config = configparser.ConfigParser()

    # Check if the config file exists, if not, create it
    if not os.path.exists("config.ini"):
        """
        config["Brokers"] = {
            "broker": "",
            "port": "",
            "username": "",
            "password": "",
            "client_id": ""
        }
        """
        with open("config.ini", "w") as configfile:
            config.write(configfile)
    devicesRAM = []           
    initialize_database()
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())
