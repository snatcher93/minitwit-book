# -*- coding: utf-8 -*-
"""
    MiniTwit

    A microblogging application written with Flask and sqlite3

    :copyright: (c) 2010 by Armin Ronacher.
    :license: BSD, see LICENSE for more details
"""
from flask import Flask, session, g, url_for, redirect, request, flash, render_template, abort
import sqlite3
from contextlib import closing
from werkzeug import generate_password_hash, check_password_hash
import time
from hashlib import md5

# 설정 변수
# 대문자로 된 값들은 상수로 판단되고 app.config.from_object에 의해 로드됨
# 나중에 app.config['DATABASE']와 같이 접근 가능
DATABASE = '/tmp/minitwit.db'
PER_PAGE = 30
DEBUG = True
SECRET_KEY = 'development key'

# Flask application 생성
app = Flask(__name__)

# config 설정 정보 읽어 들임
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)


def gravatar_url(email, size=80):
    '''Return the gravater for the given email address.'''
    return 'http://www,gravater.com/avatar/%s?d=identicon&=%d' % \
        (md5(email.strip().lower().encode('utf-8')).hexdigest(), size)


app.jinja_env.filters['gravatar'] = gravatar_url


def connect_db():
    """ Returns a new connection to the database. """
    return sqlite3.connect(app.config['DATABASE'])


def query_db(query, args=(), one=False):
    """ Queries the database and returns a list of dictionaries. """

    cur = g.db.execute(query, args)
    # 아래 문장도 결과는 동일합니다.
    # cur = g.db.cursor()
    # cur.execute(query, args  )
    rv = [dict((cur.description[idx][0], value) for idx, value in enumerate(row)) for row in cur.fetchall()]
    return (rv[0] if rv else None) if one else rv


def init_db():
    with closing(connect_db()) as db:
        with app.open_resource('schema.sql') as f:
            db.cursor().executescript(f.read())
        db.commit()


@app.before_request
def before_request():
    """
    Make sure we are connected to the database each request and look
    up the current user so that we know he's there.
    """
    g.db = connect_db()
    g.user = None
    if 'user_id' in session:
        g.user = query_db('select * from user where user_id = ?',
                          (session['user_id']), one=True)


@app.teardown_request
def teardown_request(exception):
    """ Close the database again at the end of the request """
    if hasattr(g, 'db'):
        g.db.close()


def get_user_id(username):
    rv = g.db.execute('select user_id from user where username=?',
                      [username]).fetchone()
    return rv[0] if rv else None


@app.route('/register', methods=['GET', 'POST'])
def register():
    """ Registers the user """
    if g.user:
        return redirect(url_for('timeline'))

    error = None
    if request.method == 'POST':
        if not request.form['username']:
            error = 'You have to enter a username'
        elif not request.form['email'] or \
            '@' not in request.form['email']:
            error = 'You have to enter a valid email address'
        elif not request.form['password']:
            error = 'You have to enter a password'
        elif get_user_id(request.form['username']) is not None:
            error = 'The username is already taken'
        else:
            g.db.execute('''insert into user(
                          username, email, pw_hash) values(?, ?, ?)''',
                        [request.form['username'], request.form['email'],
                         generate_password_hash(request.form['password'])])
            g.db.commit()
            flash('You were successfully registered and can login now')
            return redirect(url_for('login'))

    return render_template('register.html', error=error)


@app.route('/login', methods=['POST', 'GET'])
def login():
    """ Logs the user in """
    if g.user:
        return redirect(url_for('timeline'))

    error = None
    if request.method == 'POST':
        user = query_db('''select * from user where username = ?''', [request.form['username']], one=True)
        if user is None:
            error = 'Invalid username'
        elif not check_password_hash(user['pw_hash'], request.form['password']):
            error = 'Invalid password'
        else:
            flash('You were logged in')
            session['user_id'] = user['user_id']
            return redirect(url_for('timeline'))

    return render_template('login.html', error=error)


@app.route('/add_message/', methods=['POST'])
def add_message():
    ''' Registers a new message for the user '''
    if 'user_id' not in session:
        abort(401)

    if request.form['text']:
        g.db.execute('''insert into message(authod_id, text, pub_date)
                        values(?, ?, ?)''', (session[user_id], request.form['text'], int(time.time())))


@app.route('/<username>/follow')
def follow_user(username):
    """Adds the current user as follower of the given user."""
    if not g.user:
        abort(401)

    whom_id = get_user_id(username)
    if whom_id is None:
        abort(404)

    g.db.execute('insert into follower(who_id, whom_id) values(?, ?)',
                 [session['user_id'], whom_id])
    g.db.commit()
    flash('You are now following "%s"' % username)
    return redirect(url_for('user_timeline', username=username))


@app.route('/<username>/unfollow')
def unfollow_user(username):
    """Removes the current user as follower of the given user."""
    if not g.user:
        abort(401)

    whom_id = get_user_id(username)
    if whom_id is None:
        abort(404)

    g.db.execute('delete from follower where who_id=? and whom_id=?',
                 [session['user_id'], whom_id])
    g.db.commit()
    flash('You are not longer following "%s"' % username)
    return redirect(url_for('user_timeline', username=username))


@app.route("/public")
def public_timeline():
    """Displays the lastest message of all users."""
    return render_template('timeline.html', message=query_db('''
        select message.*, user.* from message, user
        where message.author_id = user.user_id
        order by message.pub_date desc limit?''', [PER_PAGE]))


@app.route('/')
def timeline():
    """
    Shows a users timeline of if no user is logged in it will
    redirect to the public timeline. This timeline shows the user's
    messages as well as all the messages of folloerd users.
    """
    if not g.user:
        return redirect(url_for('public_timeline'))
    return render_template('timeline.html', message=query_db('''
        select message.*, user.* from message, user
        where message.author_id = user.user_id and (
          user.user_id = ? or
          user.user_id in (select whom_id from follwer where who_id=?))
        order by message.pub_date desc limit?''',
        [session['user_id'], session['user_id'], PER_PAGE]))


@app.route('/<username>')
def user_timeline(username):
    """Displays a users tweets."""
    profile_user = query_db('select * from user where username=?',
                            [username], one=True)
    if profile_user is None:
        abort(404)
    followed = False
    if g.user:
        followed = query_db('''select 1 from follower WHERE
                    follower.who_id=? and follower_whom_id=?''',
                    [session['user_id'], profile_user['user_id']],
                    one=True) is not None
    return render_template('tineline.html', messages=query_db('''
                    select message.*, user.* from message, user
                    where message.author_id = user.user_id and user.user_id = ?
                    order by message.pub_date desc limit?''',
                    [profile_user['user_id'], PER_PAGE]), followed=followed,
                    profile_user=profile_user)


if __name__ == '__main__':
    init_db()
    app.run()
