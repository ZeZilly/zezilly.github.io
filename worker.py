from rq import Worker, Queue, Connection
from redis import Redis
from app.settings import settings

listen = [settings.RQ_QUEUE]
redis_conn = Redis.from_url(settings.REDIS_URL)

if __name__ == '__main__':
    with Connection(redis_conn):
        worker = Worker([Queue(q, connection=redis_conn) for q in listen])
        worker.work()
