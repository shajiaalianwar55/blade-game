import os  # Operating system utilities (for env vars)
import random  # Random operations for target assignment
import secrets  # Secure random generator for blade codes
import string  # String constants for character pools
import copy  # Deep copy for resetting game state
from functools import wraps  # Decorator helper to preserve function metadata
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify  # Flask web framework

# Initialize Flask app
app = Flask(__name__)  # Create Flask application instance
app.secret_key = os.getenv('SECRET_KEY', 'your_secret_key')  # Secret key for sessions and flashing, from env or default

# —— OOP: Player class definition ——
class Player:
    def __init__(self, username, password, lat=0.0, lng=0.0):  # Constructor for new Player
        self.username = username  # Store player's username
        self.password = password  # Store player's password
        self.target = ""  # Who this player is assigned to kill
        self.alive = True  # Is player still alive?
        self.blade_code = generate_blade_code()  # Unique code for confirming kills
        self.kill_count = 0  # Number of successful kills
        self.blades = 1  # Number of blades (loot) carried
        self.killed_by = None  # Username of who killed this player
        self.location = {"lat": lat, "lng": lng}  # GPS coordinates

    def kill(self, target_player):  # Method to process a kill
        target_player.alive = False  # Mark the target as dead
        target_player.killed_by = self.username  # Record killer's username
        self.kill_count += 1  # Increment killer's kill count
        self.blades += target_player.blades  # Transfer blades from target to killer
        target_player.blades = 0  # Zero out target's blades

# Helper to generate fixed-length blade codes
def generate_blade_code(length=5):  # Function to create random code
    chars = string.ascii_uppercase + string.digits  # Pool: A-Z and 0-9
    return ''.join(secrets.choice(chars) for _ in range(length))  # Build code

# 🔹 Initial players setup with Player objects
players = {
    'sara': Player('sara', '1234', 31.5135, 74.3630),  # Sara's profile
    'hira': Player('hira', '1234', 31.5140, 74.3625),  # Hira's profile
    'fatima': Player('fatima', '1234', 31.5138, 74.3628),  # Fatima's profile
    'sana': Player('sana', '1234', 31.5132, 74.3632)  # Sana's profile
}

# 🔹 Keep a deep-copy of originals for reset
_initial_players = copy.deepcopy(players)  # Store initial state

# 🔹 Admin credentials map
auth_admins = {'admin': 'adminpass'}  # Admin username->password

# —— Decorators for access control ——
def login_required(f):  # Decorator to require login
    @wraps(f)  # Preserve metadata
    def wrapped(*args, **kwargs):  # Wrapper function
        if 'username' not in session:  # If not logged in
            return redirect(url_for('login'))  # Go to login page
        return f(*args, **kwargs)  # Otherwise proceed
    return wrapped  # Return wrapped function

def admin_required(f):  # Decorator to require admin privileges
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get('username') not in auth_admins:  # If not admin
            return redirect(url_for('login'))  # Redirect to login
        return f(*args, **kwargs)  # Otherwise proceed
    return wrapped

# —— Public routes ——
@app.route('/')  # Home page route
def home():
    return render_template('home.html')  # Show landing page

@app.route('/register', methods=['GET','POST'])  # User registration route
def register():
    if request.method == 'POST':  # If form submitted
        username = request.form['username'].lower()  # Normalize username
        password = request.form['password']  # Get password
        if username in players or username in auth_admins:  # If already exists
            flash('Username taken.', 'warning')  # Warn user
            return render_template('register.html')  # Reload form
        # Create new Player object and add to players
        players[username] = Player(username, password)
        flash(f'Account created for {username}!', 'success')  # Success message
        return redirect(url_for('login'))  # Go to login
    return render_template('register.html')  # Show registration form

@app.route('/login', methods=['GET','POST'])  # User login route
def login():
    if request.method == 'POST':  # Form submitted
        username = request.form['username'].lower()  # Normalize
        password = request.form['password']  # Get pwd
        if username in players and players[username].password == password:  # Player login
            session['username'] = username  # Save session
            return redirect(url_for('dashboard'))  # Go to dashboard
        if username in auth_admins and auth_admins[username] == password:  # Admin login
            session['username'] = username  # Save session
            return redirect(url_for('admin_dashboard'))  # Go to admin panel
        flash('Invalid credentials.', 'danger')  # Show error
        return render_template('login.html', logged_out=False)  # Reload login
    logged_out = (request.args.get('logged_out') == '1')  # Check logout flag
    return render_template('login.html', logged_out=logged_out)  # Show login form

@app.route('/logout')  # User logout route
def logout():
    session.pop('username', None)  # Remove username from session safely
    return redirect(url_for('login', logged_out=1))  # Redirect with logout flag

# —— Location endpoints ——
@app.route('/location/<username>')  # Get user location route
@login_required
def get_location(username):
    info = players.get(username.lower())  # Lookup Player object
    if not info:  # If not found
        return jsonify({'error': 'User not found'}), 404  # Return JSON error
    return jsonify(info.location)  # Return location dict

@app.route('/update_location', methods=['POST'])  # Update location route
@login_required
def update_location():
    data = request.get_json()  # Reads and converts the JSON the client sent you into a normal Python dictionary called data
    lat, lng = data.get('lat'), data.get('lng')  # Extract coords
    if lat is None or lng is None:  # if one of them is missing
        return jsonify({'error': 'Missing lat or lng'}), 400  # Bad request
    # Update current user's location
    players[session['username']].location = {'lat': lat, 'lng': lng}
    return jsonify({'status': 'updated', 'location': players[session['username']].location})  # Confirm

# —— Unified dashboard ——
@app.route('/dashboard', methods=['GET','POST'])  # Player dashboard route
@login_required
def dashboard():
    user = session['username']  # Logged-in username
    if user in auth_admins:  # If admin
        return redirect(url_for('admin_dashboard'))  # Admin view

    if request.method == 'POST':  # Kill submission
        player = players[user]  # Get Player object
        target_name = player.target  # Who they're hunting
        if target_name and request.form['blade_code'] == players[target_name].blade_code:  # Correct code
            killer = player  # Shorthand
            victim = players[target_name]  # Victim object
            killer.kill(victim)  # Use Player.kill() method
            # Reassign next target in a circular list
            alive_list = [u for u,p in players.items() if p.alive]  # Alive usernames
            idx = alive_list.index(user)  # Find current index
            next_target = alive_list[(idx + 1) % len(alive_list)] if len(alive_list) > 1 else ''  # Next target
            killer.target = next_target  # Assign it
            flash('Kill confirmed!', 'success')  # Success message
        else:
            flash('Incorrect blade code.', 'danger')  # Error message
        return redirect(url_for('dashboard'))  # Refresh page

    # Winner or eliminated views
    alive_list = [u for u,p in players.items() if p.alive]  # Alive usernames
    if len(alive_list) == 1 and alive_list[0] == user:  # Only you left
        return render_template('winner.html', name=user.capitalize())  # Show winner page
    if not players[user].alive:  # If you're dead
        p = players[user]  # Your Player object
        return render_template(
            'eliminated.html',
            name=user.capitalize(),
            killer=p.killed_by.capitalize() if p.killed_by else None,
            blade_code=p.blade_code,
            kill_count=p.kill_count,
            blades=p.blades
        )  # Show eliminated page

    # Normal dashboard view
    p = players[user]  # Your Player object
    return render_template(
        'dashboard.html',
        name=user.capitalize(),
        blade_code=p.blade_code,
        kill_count=p.kill_count,
        blades=p.blades,
        target=p.target.capitalize() if p.target else None,
        players=players  # Full players dict for maps or lists
    )  # Show dashboard

# —— Leaderboard ——
@app.route('/leaderboard')  # Leaderboard route
@login_required
def leaderboard():
    # Sort by kill count descending
    kills_board = sorted(
        [(u.capitalize(), p.kill_count) for u,p in players.items()],
        key=lambda x: x[1], reverse=True
    )
    # Sort by blades count descending
    blades_board = sorted(
        [(u.capitalize(), p.blades) for u,p in players.items()],
        key=lambda x: x[1], reverse=True
    )
    return render_template('leaderboard.html', kills_board=kills_board, blades_board=blades_board)  # Show leaderboard

# —— Admin Dashboard ——
@app.route('/admin/dashboard')  # Admin dashboard route
@admin_required
def admin_dashboard():
    # Prepare data for admin view
    admin_view = [
        {'name': u.capitalize(), 'code': p.blade_code,
         'kills': p.kill_count, 'blades': p.blades, 'alive': p.alive}
        for u,p in players.items()
    ]
    active_count = sum(1 for p in players.values() if p.alive)  # Count alive players
    return render_template('admin_dashboard.html', admin_view=admin_view, active_count=active_count)  # Show admin panel

# —— Admin: Remove Player ——
@app.route('/admin/remove/<username>', methods=['POST'])  # Remove player route
@admin_required
def admin_remove(username):
    key = username.lower()  # Normalize
    if key in players:  # If exists
        p = players[key]  # Player object
        p.alive = False  # Kill them
        p.killed_by = None  # No killer assigned
        flash(f"{username} removed from game.", 'info')  # Notify admin
    return redirect(url_for('admin_dashboard'))  # Refresh admin

# —— Admin: Assign Targets ——
@app.route('/admin/assign_targets', methods=['POST'])  # Assign targets route
@admin_required
def admin_assign():
    alive_list = [u for u,p in players.items() if p.alive]  # Alive usernames
    if len(alive_list) < 2:  # Not enough players
        flash('Not enough players.', 'warning')  # Warn admin
        return redirect(url_for('admin_dashboard'))  # Refresh
    random.shuffle(alive_list)  # Shuffle order
    # Circular assignment
    for idx, u in enumerate(alive_list):
        players[u].target = alive_list[(idx + 1) % len(alive_list)]  # Next on list
    flash('Targets assigned!', 'success')  # Notify admin
    return redirect(url_for('admin_dashboard'))  # Refresh

# —— Admin: Reset Game ——
@app.route('/admin/reset', methods=['POST'])  # Reset route
@admin_required
def admin_reset():
    global players  # Modify global
    players = copy.deepcopy(_initial_players)  # Restore initial players
    flash('Game reset to initial test players.', 'info')  # Notify admin
    return redirect(url_for('admin_dashboard'))  # Back to admin panel

# Entrypoint
if __name__ == '__main__':  # If run directly
    app.run(debug=True)  # Start Flask in debug mode
