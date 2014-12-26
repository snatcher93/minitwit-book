# -*- coding: utf-8 -*-
"""
    MiniTwit

    A microblogging application written with Flask and sqlite3

    :copyright: (c) 2010 by Armin Ronacher.
    :license: BSD, see LICENSE for more details
"""
from flask import Flask, session, g, url_for, redirect, request, flash, render_template
import sqlite3
from contextlib import closing
from werkzeug import generate_password_hash, check_password_hash

# configuration
DATABASE = '/tmp/minitwit.db'
PER_PAGE = 30
DEBUG = True
SECRET_KEY = 'development key'


app = Flask(__name__)
app.config.from_object(__name__)
app.config.from_envvar('MINITWIT_SETTINGS', silent=True)


def connect_db():
    """ Returns a new connection to the database. """
    return sqlite3.connect(app.config['DATABASE'])


def query_db(query, args=(), one=False):
    """ Queries the database and returns a list of dictionaries. """

    cur = g.db.execute(query, args)
    # 아래 문장도 결과는 동일합니다.
    # cur = g.db.cursor()
    # cur.execute(query, args)
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


@app.route('/')
def timeline():
    pass

if __name__ == '__main__':
    init_db()
    app.run()
