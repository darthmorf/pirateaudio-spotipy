
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
from requests.exceptions import ReadTimeout
from PIL import Image
from PIL import ImageDraw
from io import BytesIO
import ST7789 as ST7789 
import time
import RPi.GPIO as GPIO
from threading import Thread


class PirateHat:

    buttons =      [ 5,   6,   16,  24]
    buttonLabels = ['A', 'B', 'X', 'Y']
    running = False

    apiKeyFile = "./spotifykeys.txt"

    spotify = None
    disp = None
    imageSize = None
    last_track = None
    image = None
    blankImage = None
    loopThread = None
    backlight = None

    def __init__(self):
        # Setup Spotify
        scope = "user-read-currently-playing user-read-playback-state app-remote-control user-modify-playback-state"

        with open(self.apiKeyFile, 'r') as file:
            clientId = file.readline().replace("\n", "")
            clientSecret = file.readline().replace("\n", "")

        self.spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=clientId, client_secret=clientSecret, redirect_uri="http://localhost", scope=scope))

        # Init display
        self.disp = ST7789.ST7789(
            height=240,
            width=240,
            rotation=270,
            port=0,
            cs=1,
            dc=9,
            backlight=13,
            spi_speed_hz=60 * 1000 * 1000,
            offset_left=0,
            offset_top=0
        )
        self.disp.begin()

        self.imageSize = (self.disp.width, self.disp.height)
        self.blankImage = Image.new('RGB', self.imageSize, color=(0, 0, 0))
        self.image = self.blankImage

        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        # Buttons
        GPIO.setup(self.buttons, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        for pin in self.buttons:
            GPIO.add_event_detect(pin, GPIO.FALLING, self.handle_button, bouncetime=100)

        # Backlight Pin
        GPIO.setup(13, GPIO.OUT)
        self.backlight = GPIO.PWM(13, 500)
        self.backlight.start(100)

        # Setup loop thread
        self.loopThread = Thread(target=self.loop)
        self.loopThread.start()

        
    def start(self):
        self.running = True

    def stop(self):
        seld.running = False


    def handle_button(self, pin):
        label = self.buttonLabels[self.buttons.index(pin)]
        
        if self.spotify == None:
            return

        if label == "A":
            self.play_pause()
        elif label == "B":
            self.skip_next_track()
        elif label == "Y":
            self.skip_last_track()

    def play_pause(self):
        current_track = self.spotify.current_playback(additional_types=["episode"])

        if current_track and current_track["is_playing"]:
            self.spotify.pause_playback()
        else:
            self.spotify.start_playback()

    def skip_next_track(self):
        self.spotify.next_track()


    def skip_last_track(self):
        self.spotify.previous_track()


    def loop(self):
        throttle = 0.25

        while True:

            # Get the current album art if running
            if self.running:
                self.image = self.get_current_album_image()
                self.backlight.ChangeDutyCycle(100)
            # Otherwise get nothing
            else:
                self.image = self.blankImage
               
            # Turn off the display if the image is blank
            if self.image == self.blankImage:
                self.backlight.ChangeDutyCycle(0)

            # Update the display
            self.disp.display(self.image)
            time.sleep(throttle)


    def get_current_album_image(self):
        try:
        
            # Get currently playing
            current_track = self.spotify.current_playback(additional_types=["episode"])

            # Check if actually playing
            if current_track and current_track["is_playing"] and current_track != self.last_track:

                self.last_track = current_track

                if current_track["currently_playing_type"] == "episode":
                    url = current_track["item"]["images"][0]["url"]

                else:
                    url = current_track["item"]["album"]["images"][0]["url"]

                response = requests.get(url, timeout=10)
                im = Image.open(BytesIO(response.content)).convert('RGB')
                im = im.resize(self.imageSize)

                return im

            else:
                return self.blankImage

        except ReadTimeout:
            print("Spotify timed out...")
            return self.blankImage

        except Exception as e:
            print("Spotify Error:")
            print(e)   
            return self.blankImage



if __name__ == "__main__":
    ph = PirateHat()
    ph.start()