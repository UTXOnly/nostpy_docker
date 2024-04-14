import asyncio
import json
import logging
import os
from typing import Any, Dict, Tuple

import aiohttp
from aiohttp import web
import websockets
from aiohttp.client_exceptions import ClientConnectionError
from logging.handlers import RotatingFileHandler

import websockets.exceptions

from websocket_classes import (
    ExtractedResponse,
    TokenBucketRateLimiter,
    WebsocketMessages,
)

from opentelemetry import trace

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.instrumentation.aiohttp_client import (
    AioHttpClientInstrumentor
)

#from opentelemetry.sdk.resources import Resource
#from opentelemetry.semconv.trace import ResourceAttributes

#resource = Resource(attributes={
#    ResourceAttributes.SERVICE_NAME: service_name,
#    # Include any other relevant attributes
#})

AioHttpClientInstrumentor().instrument()

#create your FastAPI app

trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

otlp_exporter = OTLPSpanExporter()
span_processor = BatchSpanProcessor(otlp_exporter) # we don't want to export every single trace by itself but rather batch them
otlp_tracer = trace.get_tracer_provider().add_span_processor(span_processor)




logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

async def health_check(request):
    return web.Response(text="OK",status=200)

domain_name = "nostpy.serverless-nostr.com"
version = 0.8
contact = "bh419@protonmail.com"
hex_pubkey = "4503baa127bdfd0b054384dc5ba82cb0e2a8367cbdb0629179f00db1a34caacc"



async def get_data(http_accept):
    if http_accept and "application/nostr+json" in http_accept.lower():
        return web.json_response({
            "name": "{domain_name}",
            "description": "NostPy relay {version}",
            "pubkey": "{hex_pubkey}",
            "contact": "{contact}",
            "supported_nips": [1, 2, 4, 9, 15, 16, 25, 50, 99],
            "software": "git+https://github.com/UTXOnly/nost-py.git",
            "version": "{version}",
            "site": "https://image.nostr.build/ca2fd20bdd90fe91525ffdd752a2773eb85c2d5a144154d4a0e6227835fa4ae1.jpg"
        }, status=200)
    else:
        return {"message": "Not Found"}



async def handle_websocket_connection(
    websocket: websockets.WebSocketServerProtocol,
) -> None:
    conn = aiohttp.TCPConnector(limit=500)
    async with aiohttp.ClientSession(connector=conn) as session:
        try:
            async for message in websocket:
                try:
                    logger.debug(f"message in loop is {message}")
                    ws_message = message
                    if ws_message:
                        ws_message = WebsocketMessages(
                            message=json.loads(message),
                            websocket=websocket,
                            logger=logger,
                        )
                except json.JSONDecodeError as json_error:
                    logger.error(f"Error decoding JSON message: {json_error}")
                    continue

                #statsd.increment(
                #    "nostr.new_connection.count",
                #    tags=[
                #        f"client_ip:{ws_message.obfuscated_client_ip}",
                #        f"nostr_client:{ws_message.origin}",
                #    ],
                #)

                if not await rate_limiter.check_request(
                    ws_message.obfuscated_client_ip
                ):
                    logger.warning(
                        f"Rate limit exceeded for client: {ws_message.obfuscated_client_ip}"
                    )
                    rate_limit_response = (
                        "OK",
                        "nostafarian419",
                        "false",
                        "rate-limited: slow your roll nostrich",
                    )
                    #statsd.increment(
                    #    "nostr.client.rate_limited.count",
                    #    tags=[
                    #        f"client_ip:{ws_message.obfuscated_client_ip}",
                    #        f"nostr_client:{ws_message.origin}",
                    #    ],
                    #)
                    await websocket.send(json.dumps(rate_limit_response))
                    await websocket.close()
                    return

                if ws_message.event_type == "EVENT":
                    logger.debug(
                        f"Event to be sent payload is: {ws_message.event_payload} of type {type(ws_message.event_payload)}"
                    )
                    with tracer.start_as_current_span("send_event_to_handle") as span:
                        current_span = trace.get_current_span()
                        current_span.set_attribute("operation.name", "send.event.handler")
                        await send_event_to_handler(
                            session=session,
                            event_dict=dict(ws_message.event_payload),
                            websocket=websocket,
                        )
                elif ws_message.event_type == "REQ":
                    logger.debug("Entering REQ branch")
                    logger.debug(
                        f"Payload is {ws_message.event_payload} and of type: {type(ws_message.event_payload)}"
                    )
                    with tracer.start_as_current_span("send_event_to_subscription") as span:
                        current_span = trace.get_current_span()
                        current_span.set_attribute("operation.name", "send.event.subscription")
                        await send_subscription_to_handler(
                            session=session,
                            event_dict=ws_message.event_payload,
                            subscription_id=ws_message.subscription_id,
                            websocket=websocket,
                        )
                elif ws_message.event_type == "CLOSE":
                    response: Tuple[str, str] = (
                        "CLOSED",
                        ws_message.subscription_id,
                        "error: shutting down idle subscription",
                    )
                    await websocket.send(json.dumps(response))

        except websockets.exceptions.ConnectionClosedError as close_error:
            logger.error(
                f"WebSocket connection closed unexpectedly: {close_error}",
                exc_info=True,
            )

        except ClientConnectionError as connection_error:
            logger.error(
                f"Connection error occurred: {connection_error}", exc_info=True
            )

        except aiohttp.ClientError as client_error:
            logger.error(f"HTTP client error occurred: {client_error}", exc_info=True)

        except Exception as e:
            logger.error(
                f"Error occurred while processing WebSocket message: {e}", exc_info=True
            )


async def send_event_to_handler(
    session: aiohttp.ClientSession,
    event_dict: Dict[str, Any],
    websocket: websockets.WebSocketServerProtocol,
) -> None:
    url: str = "http://localhost/new_event"


    try:
        async with session.post(url, data=json.dumps(event_dict)) as response:
            current_span = trace.get_current_span()
            current_span.set_attribute("operation.name", "post.event.handler")
            response_data: Dict[str, Any] = await response.json()
            logger.debug(
                f"Received response from Event Handler {response_data}, data types is {type(response_data)}"
            )
            response_object = ExtractedResponse(response_data, logger)
            if response.status:
                formatted_response = await response_object.format_response()
                await websocket.send(json.dumps(formatted_response))
    except Exception as e:
        logger.error(f"An error occurred while sending the event to the handler: {e}")


async def send_subscription_to_handler(
    session: aiohttp.ClientSession,
    event_dict: Dict,
    subscription_id: str,
    websocket: websockets.WebSocketServerProtocol,
) -> None:
    url: str = "http://localhost/subscription"
    payload: Dict[str, Any] = {
        "event_dict": event_dict,
        "subscription_id": subscription_id,
    }
    async with session.post(url, data=json.dumps(payload)) as response:
        current_span = trace.get_current_span()
        current_span.set_attribute("operation.name", "post.event.subscription")
        response_data = await response.json()
        logger.debug(
            f"Data type of response_data: {type(response_data)}, Response Data: {response_data}"
        )
        if not response_data:
            logger.debug("Response data none, returning")
            await websocket.send(json.dumps(["EOSE", subscription_id]))
            return
        response_object = ExtractedResponse(response_data, logger)
        EOSE = "EOSE", response_object.subscription_id

        if response.status == 200 and response_object.event_type == "EVENT":
            with tracer.start_as_current_span("format_response") as span:
                current_span = trace.get_current_span()
                current_span.set_attribute("operation.name", "format.response")
                response_list = await response_object.format_response()
            with tracer.start_as_current_span("send event loop") as span:
                current_span = trace.get_current_span()
                current_span.set_attribute("operation.name", "send.event.loop")

                await response_object.send_event_loop(response_list, websocket)
                await websocket.send(json.dumps(EOSE))
        else:
            await websocket.send(json.dumps(EOSE))
            logger.debug(f"Response data is {response_data} but it failed")

#if __name__ == "__main__":
#    rate_limiter = TokenBucketRateLimiter(tokens_per_second=1, max_tokens=50000)
#
#    try:
#        start_server = websockets.serve(handle_websocket_connection, "0.0.0.0", 8008)
#        asyncio.get_event_loop().run_until_complete(start_server)
#        asyncio.get_event_loop().run_forever()
#
#    except Exception as e:
#        logger.error(f"Error occurred while starting the server main loop: {e}")
async def main():
    # Create an HTTP application
    app = web.Application()
    app.router.add_get('/health', health_check)  # Add health check endpoint
    app.router.add_get('/', get_data)


    # Start the WebSocket server
    websocket_server = websockets.serve(handle_websocket_connection, "0.0.0.0", 8008)

    # Run both servers concurrently
    await asyncio.gather(websocket_server, web._run_app(app, port=81))

if __name__ == "__main__":

    try:
        rate_limiter = TokenBucketRateLimiter(tokens_per_second=1, max_tokens=50000)
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
