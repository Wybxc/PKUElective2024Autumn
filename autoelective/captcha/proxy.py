#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Filename : proxy
# @Date : 2022-09-05
# @Project: PKUElective2022Spring
# @AUTHOR : Totoro
import asyncio
import json
from collections import Counter


import aiohttp

from autoelective.captcha import TTShituRecognizer
from autoelective.captcha.online import APIConfig

_RECOGNIZER_URL = "http://api.ttshitu.com/base64"

RECOGNITION_METHODS = [3, 1003, 7]
RECOGNITION_WEIGHT = {3: 0.4, 1003: 0.7, 7: 1.0}


class RecognitionProxy(object):
    def __init__(self):
        self._config = APIConfig()
        # Initialize connection pool
        self.conn = aiohttp.TCPConnector(limit_per_host=100, limit=0, ttl_dns_cache=300)
        self.PARALLEL_REQUESTS = 100
        self.results = []
        self.queue = []

    def msg_pack(self, raw, typeid):
        encoded = TTShituRecognizer.to_b64(raw)
        data = {
            "username": self._config.uname,
            "password": self._config.pwd,
            "image": encoded,
            "typeid": typeid
        }
        return data

    async def gather_with_concurrency(self, trials):
        semaphore = asyncio.Semaphore(self.PARALLEL_REQUESTS)
        session = aiohttp.ClientSession(connector=self.conn)

        async def concurrent_post(content):
            async with semaphore:
                try:
                    async with session.post(_RECOGNIZER_URL, json=content, timeout=self._config.timeout) as response:
                        obj = json.loads(await response.read())
                        self.results.append((obj, content['typeid']))
                except asyncio.exceptions.TimeoutError as e:
                    print(f"Timeout with method {content['typeid']}")

        await asyncio.gather(*(concurrent_post(trial) for trial in trials))
        await session.close()

    def recognize(self, raw):
        base_msg = self.msg_pack(raw, self._config.typeid)
        for method in RECOGNITION_METHODS:
            temp = base_msg.copy()
            temp["typeid"] = method
            self.queue.append(temp)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.gather_with_concurrency(self.queue))
        self.conn.close()
        print(f"Completed {len(self.queue)} requests with {len(self.results)} results")
        container = [(res[0]['data']['result'], res[1]) for res in self.results]
        unique_res = Counter([res[0] for res in container]).keys()
        count_dict = {}
        for i in unique_res:
            count_dict.update({i: 0})
        for res in container:
            count_dict[res[0]] += RECOGNITION_WEIGHT[res[1]]
        return [key for key, value in count_dict.items() if value == max(count_dict.values())][0]


if __name__ == '__main__':
    with open("samples/test.png", "rb") as image_file:
        encoded_string = image_file.read()
    proxy = RecognitionProxy()
    proxy.recognize(encoded_string)
