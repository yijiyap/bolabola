# from flask import Flask, jsonify, request

import quart_flask_patch
from quart import Quart, jsonify, request


# SQLAlchemy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, Column, Integer, String, JSON, select
from sqlalchemy.orm.attributes import flag_modified

# SQLAlchemy Asynchronous
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Others
import pika
import os
import json
from threading import Thread
from flask_cors import CORS

# Asynchronous things
import asyncio
import aio_pika
import aiomysql


## AMQP items ################################################################################################
async def on_message(message: aio_pika.IncomingMessage):
    async with message.process():
        print(f"Received message: {message.body.decode()}")


async def amqp():
    rabbitmq_url = "amqp://ticketboost:veryS3ecureP@ssword@rabbitmq/"
    connection = await aio_pika.connect_robust(rabbitmq_url)
    channel = await connection.channel()
    queue = await channel.declare_queue("user", durable=True)
    await queue.consume(on_message)
    print("RabbitMQ consumer started")
    await asyncio.Future()  # Run forever


## AMQP items end ################################################################################################

## OLD SQL Alchemy Code ################################################################################################
# app = Flask(__name__)
# app.config["SQLALCHEMY_DATABASE_URI"] = (
#     "mysql+mysqlconnector://ticketboost:veryS3ecurePassword@mysql:3306/bolabola_user"
# )
# app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = True
# db = SQLAlchemy()
# db = db.init_app(app)
# db.app = app

##  Old Model Code
# class User(db.Model):
#     __tablename__ = "user"
#     id = db.Column(db.String(120), primary_key=True)
#     name = db.Column(db.String(80), nullable=False)
#     email = db.Column(db.String(120), unique=True, nullable=False)
#     tickets = db.Column(db.JSON, nullable=True)
#     premium = db.Column(db.String(80), nullable=False)

#     def __init__(self, id, name, email, tickets, premium):
#         self.id = id
#         self.name = name
#         self.email = email
#         self.tickets = tickets
#         self.premium = premium

#     def json(self):
#         return {
#             "id": self.id,
#             "name": self.name,
#             "email": self.email,
#             "tickets": self.tickets,
#             "premium": self.premium,
#         }
## OLD SQL Alchemy Code end ################################################################################################


app = Quart(__name__)
DATABASE_URL = (
    "mysql+aiomysql://ticketboost:veryS3ecurePassword@mysql:3306/bolabola_user"
)

engine = create_async_engine(DATABASE_URL, echo=True)

# Create a base class for your models
Base = declarative_base()

# Configure Session class to use AsyncSession
AsyncSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)


class User(Base):
    __tablename__ = "user"
    id = Column(String(120), primary_key=True)
    name = Column(String(80), nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    tickets = Column(JSON, nullable=True)
    premium = Column(String(80), nullable=False)

    def __init__(self, id, name, email, tickets, premium):
        self.id = id
        self.name = name
        self.email = email
        self.tickets = tickets
        self.premium = premium

    def json(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "tickets": self.tickets,
            "premium": self.premium,
        }


# path to test if the service is running
@app.route("/ping", methods=["GET"])
async def ping():
    print("pinged")
    return "pong"


############################################################################################################
#########################################    VIEW ALL USER INFO    #########################################
############################################################################################################
# path to print all users
@app.route("/", methods=["GET"])
async def home():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(select(User))
            userlist = result.scalars().all()
            if len(userlist) == 0:
                return jsonify({"code": 404, "message": "No users found"})
            data = [user.json() for user in userlist]
            return jsonify({"code": 200, "data": data})


############################################################################################################
###############################    VIEW PARTICULAR USER INFO    ###########################################
############################################################################################################
# view particular user's info, given by user_id
@app.route("/<int:id>", methods=["GET"])
async def view_user(id):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, str(id))
        if user is None:
            return jsonify({"code": 404, "message": "User not found"})
        return jsonify({"code": 200, "data": user.json()})


############################################################################################################
########################################    CREATE USER     ################################################
############################################################################################################
# path to check if user exists, and to create a new user if not.
@app.route("/check-create", methods=["POST"])
async def check_create_user():
    """
    This method creates a new user using the info received by Auth0.
    Sample payload:
    {
        "name": "John Doe",
        "email": "johndoe@example.com",
        "user_id": "auth0|1234"
    }
    """
    data = await request.get_json()  # Asynchronously get the JSON data from the request
    if data is None:
        return jsonify({"code": 400, "message": "User info not provided"})

    received_user_id = data["user_id"]

    # Use an async session to interact with the database
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Asynchronously query for an existing user
            existing_user = await session.execute(
                select(User).filter_by(id=received_user_id)
            )
            user = existing_user.scalars().first()

            if user is not None:
                # If user exists, return an error message
                return jsonify({"code": 400, "message": "User already exists"})

            # If user does not exist, create a new User instance
            new_user = User(
                id=received_user_id,
                name=data["name"],
                email=data["email"],
                tickets=None,
                premium="N",
            )

            # Add the new user to the session and commit the changes asynchronously
            session.add(new_user)
            await session.commit()

    return jsonify({"code": 201, "message": "User created successfully"})


############################################################################################################
##################################    VIEW USER TICKETS     ################################################
############################################################################################################
# view all tickets bought by the user
@app.route("/<int:id>/tickets", methods=["GET"])
async def view_all_user_tickets(id):
    """
    This method returns all the tickets owned by the user.
    Query will join the User and Ticket tables and return the tickets owned by the user.
    """
    user = User.query.get(str(id))
    if user is None:
        return jsonify({"code": 404, "message": "User not found"})
    if user.tickets is None:
        return jsonify({"code": 404, "message": "User has no tickets"})
    return jsonify({"code": 200, "data": user.tickets})


# view a specific ticket bought by the user by serial number
@app.route("/<int:id>/tickets/<int:serial_no>", methods=["GET"])
async def view_ticket_by_serial_no(id, serial_no):
    """
    This method returns the details of a specific ticket owned by the user.
    """
    user = User.query.get(str(id))
    if user is None:
        return jsonify({"code": 404, "message": "User not found"})
    if user.tickets is None:
        return jsonify({"code": 404, "message": "User has no tickets"})
    for ticket in user.tickets:
        if ticket["serial_no"] == str(serial_no):
            return jsonify({"code": 200, "data": ticket})
    return jsonify({"message": "Ticket not found"})


# view a specific ticket bought by the user by match id
@app.route("/<int:id>/tickets/match/<int:match_id>", methods=["GET"])
async def view_ticket_by_match_id(id, match_id):
    """
    This method returns the details of a specific ticket owned by the user.
    """
    user = User.query.get(str(id))
    if user is None:
        return jsonify({"code": 404, "message": "User not found"})
    if user.tickets is None:
        return jsonify({"code": 404, "message": "User has no tickets"})
    for ticket in user.tickets:
        if ticket["match_id"] == str(match_id):
            return jsonify({"code": 200, "data": ticket})
    return jsonify({"code": 404, "message": "Ticket not found"})


############################################################################################################
#################################    END OF VIEW USER TICKETS    ###########################################
############################################################################################################


############################################################################################################
####################################    ADD A USER TICKET     ##############################################
############################################################################################################
# add a ticket to the user's list of tickets
@app.route("/<int:id>/tickets", methods=["POST"])
async def add_ticket_to_user(id):
    """
    This method adds a ticket to the user's list of tickets.
    Sample ticket:
    {
        "match_id": "1",
        "ticket_category": "A",
        "serial_no": "100"
    }
    """
    ticket = request.json
    if ticket is None:
        return jsonify({"code": 400, "message": "Ticket info not provided"})
    user = User.query.get(str(id))
    if user is None:
        return jsonify({"code": 404, "message": "User not found"})

    # check if the user already has the ticket
    if user.tickets is not None:
        for t in user.tickets:
            if t["serial_no"] == ticket["serial_no"]:
                return jsonify({"code": 400, "message": "User already has the ticket"})

    # add the ticket to the user's list of tickets
    if user.tickets is None:
        user.tickets = [ticket]
    else:
        user.tickets.append(ticket)

    # inform sqlalchemy that the tickets attribute has been modified. This MUST BE DONE because sqlalchemy got problem with JSON
    flag_modified(user, "tickets")

    db.session.commit()
    return jsonify({"code": 201, "message": "Ticket added successfully"})


############################################################################################################
####################################    END OF ADD A USER TICKET     #######################################
############################################################################################################


############################################################################################################
####################################    DELETE A USER TICKET     ###########################################
############################################################################################################
# delete a ticket from the user's list of tickets
@app.route("/<int:id>/tickets/<int:serial_no>", methods=["DELETE"])
async def delete_ticket_from_user(id, serial_no):
    """
    This method deletes a ticket from the user's list of tickets.
    This will be used when the user refunds a ticket successfully.
    """
    user = User.query.get(str(id))
    if user is None:
        return jsonify({"code": 404, "message": "User not found"})
    if user.tickets is None:
        return jsonify({"code": 404, "message": "User has no tickets"})
    for ticket in user.tickets:
        if ticket["serial_no"] == str(serial_no):
            user.tickets.remove(ticket)
            flag_modified(user, "tickets")
            db.session.commit()
            return jsonify({"code": 200, "message": "Ticket deleted successfully"})
    return jsonify({"code": 404, "message": "Ticket not found"})


############################################################################################################
####################################    END OF DELETE A USER TICKET     ####################################
############################################################################################################


############################################################################################################
######################################    RABBITMQ INFO    #################################################
############################################################################################################
# Start a RabbitMQ consumer to listen for refund events
# def start_rabbitmq_consumer():
#     credentials = pika.PlainCredentials("ticketboost", "veryS3ecureP@ssword")
#     parameters = pika.ConnectionParameters("rabbitmq", 5672, "/", credentials)
#     connection = pika.BlockingConnection(parameters)
#     channel = connection.channel()
#     channel.basic_consume(
#         queue="user", on_message_callback=printsomething(), auto_ack=True
#     )
#     print("RabbitMQ consumer started")
#     channel.start_consuming()


def callback(ch, method, properties, body):
    print("Callback method called")
    # parse received message
    data = json.loads(body)
    user = User.query.get(data["user_id"])
    if user is None:
        print("User not found")
        return

    def del_ticket_from_user(user, serial_no):
        for ticket in user.tickets:
            if ticket["serial_no"] == str(serial_no):
                user.tickets.remove(ticket)
                flag_modified(user, "tickets")
                db.session.commit()
                print("Ticket deleted successfully")
                return
        print("Ticket not found")

    if data["status"] == "succeeded":
        # start a new thread for database operations
        # this is because database operations are not thread safe
        refund_thread = Thread(
            target=del_ticket_from_user, args=(user, data["serial_no"])
        )
        refund_thread.start()
        print("Refund successful")
        return
    print("Refund failed")


# def run_consumer_thread():
#     consumer_thread = Thread(target=start_rabbitmq_consumer)
#     consumer_thread.daemon = True
#     consumer_thread.start()


# async def main():
#     await asyncio.gather(
#         app.run_task(host="0.0.0.0", port=9004, debug=False), # Run flask here
#         amqp(), # Run AMQp here
#     )


if __name__ == "__main__":

    async def main():
        await asyncio.gather(
            app.run_task(host="0.0.0.0", port=9004, debug=False),  # Run Quart here
            amqp(),  # Run AMQP here
        )

    asyncio.run(main())
