
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from duongdev.TO1_Chat.app import app as to1_chat_app
from duongdev.anmqpan.app import app as qpan
from duongdev.minhthy.app import app as minhthy
from duongdev.love.app import app as love
from duongdev.share.app import app as share

# This app object will be imported by the main app.py
# It will dispatch requests to the appropriate sub-app.
app = DispatcherMiddleware(None, {
    '/duongdev/to1-chat': to1_chat_app,
})

app = DispatcherMiddleware(None, {
    '/duongdev/qpan': qpan,
})

app = DispatcherMiddleware(None, {
    '/duongdev/minhthy': minhthy,
})

app = DispatcherMiddleware(None, {
    '/duongdev/love': love,
})

app = DispatcherMiddleware(None, {
    '/duongdev/share': share,
})
