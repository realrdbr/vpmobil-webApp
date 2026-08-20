# Modern VPMobil-WebApp build with Python

This is a new and modern UI for VPMobil Substitution Software. It uses the repaired python libary vpmobil-py.

## Features:
* Substitution plan from the VPMobil-Server
* Substitution info pop-up to see notes and changes in red
* Tick your lessons so that you only see your schedule
* Free room lookup
* Teacher plan

### Benefits:
No new backend required since it uses the existing Servers
Modern UI
Fetches all classes automatically
only needs set-up once with school-login-data

## Setup Guide:
1. Pull the repository with:
   ```bash
   git pull https://github.com/realrdbr/vpmobil-webApp.git
   ```
2. Install the dependencies with `pip install -r requirements.txt`
3. Rename the `.env.example` to `.env`
4. Enter the VPMobil informations and other informations to the new `.env`
5. Run the `main.py`
6. Access the website with `127.0.0.1:8000` or the changed address from the `.env`
