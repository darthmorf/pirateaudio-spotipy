
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
from requests.exceptions import ReadTimeout
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from io import BytesIO
import ST7789 as ST7789 
import time
import RPi.GPIO as GPIO
from threading import Thread
from enum import Enum
import traceback

class TextPos(Enum):
    A_Button = 0
    B_Button = 1
    X_Button = 2
    Y_Button = 3
    Title = 4

class PirateHat:

    buttons =      [ 5,   6,   16,  24]
    buttonLabels = ['A', 'B', 'X', 'Y']
    running = False
    uiToggleMode = False
    uiProgressBar = True
    uiButtonHint = False
    uiSongInfo = True

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

        # Load font for GUI
        self.font = ImageFont.truetype("NotoSans-Regular.ttf", 18)
        self.symbolFont = ImageFont.truetype("NotoEmoji.ttf", 24)

        
    def start(self):
        self.running = True

    def stop(self):
        seld.running = False


    def handle_button(self, pin):
        label = self.buttonLabels[self.buttons.index(pin)]
        
        if self.spotify == None:
            return

        if label == "X":
            self.uiToggleMode = not self.uiToggleMode

        elif not self.uiToggleMode:
            if label == "A":
                self.play_pause()
            elif label == "B":
                self.skip_next_track()
            elif label == "Y":
                self.skip_last_track()

        else:
            if label == "A":
                self.uiProgressBar = not self.uiProgressBar
            elif label == "B":
                self.uiButtonHint = not self.uiButtonHint
            elif label == "Y":
                self.uiSongInfo = not self.uiSongInfo


    def play_pause(self):
        current_track = self.spotify.current_playback(additional_types=["episode"])

        if current_track and current_track["is_playing"]:
            self.spotify.pause_playback()
            print("Paused Playback")
        else:
            self.spotify.start_playback()
            print("Resumed Playback")

    def skip_next_track(self):
        self.spotify.next_track()
        print("Skipped track")


    def skip_last_track(self):
        self.spotify.previous_track()
        print("Rewound track")


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

            uiImg = self.draw_ui()

            # Update the display
            self.disp.display(uiImg)
            time.sleep(throttle)


    def get_current_album_image(self):
        try:
        
            # Get currently playing
            current_track = self.spotify.current_playback(additional_types=["episode"])

            trackChanged = current_track and (self.last_track == None or current_track["item"]["id"] != self.last_track["item"]["id"])

            # Check if actually playing
            if current_track and current_track["is_playing"]:

                self.last_track = current_track

                if not trackChanged:
                    return self.image

                name, album, artists = self.get_track_info(current_track['item'])
                print(f"Now Playing: {name} - {album} by {artists}")

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
            print("Error:")
            traceback.print_exc()

            return self.blankImage

    def get_track_info(self, track):
        isTrack = track["type"] == "track"
        name = track["name"]
        album = ""
        artists = ""

        if isTrack:
            album = track["album"]["name"]
            for artist in track["artists"]:
                artists += artist["name"] + ", "
            artists = artists[:-2]
        else:
            album = track["show"]["name"]
            artists = track["show"]["publisher"]

        return name, album, artists


    def draw_ui(self):
        self.uiFgColor = (255,255,255,128)
        self.uiBgColor = (0,0,0,128)

        uiImg = self.image.copy()
        draw = ImageDraw.Draw(uiImg, "RGBA")

        self.xPadding = 6
        self.yPadding = 3
        self.borderpadding = 4

        if self.last_track == None:
            return uiImg

        # Draw settings UI
        if self.uiToggleMode:
            uiImg = self.draw_text(uiImg, "Configure UI", TextPos.Title, self.font, self.borderpadding)
            uiImg = self.draw_text(uiImg, "Song Info", TextPos.Y_Button, self.font, self.borderpadding)
            uiImg = self.draw_text(uiImg, "Close Menu", TextPos.X_Button, self.font, self.borderpadding)
            uiImg = self.draw_text(uiImg, "Buttons", TextPos.B_Button, self.font, self.borderpadding)
            uiImg = self.draw_text(uiImg, "Progress", TextPos.A_Button, self.font, self.borderpadding)


        # Draw general UI
        else:

            if self.uiProgressBar:
                progress = float(self.last_track["progress_ms"])
                duration = self.last_track["item"]["duration_ms"]
                pctPlayed = progress / duration

                
                bgheight = 12
                fgoffset = self.borderpadding
                bgwidth = self.imageSize[1] - self.xPadding * 2
                radius = 4

                bgx0 = self.xPadding
                bgx1 = bgx0 + bgwidth
                bgy0 = self.imageSize[1] - self.yPadding - bgheight
                bgy1 = bgy0 + bgheight

                fgx0 = bgx0 + fgoffset
                fgx1 = fgx0 + int((bgwidth - fgoffset * 2) * pctPlayed)
                fgy0 = bgy0 + fgoffset
                fgy1 = fgy0 + bgheight - 2 * fgoffset        

                #bg
                draw.rounded_rectangle(xy=(bgx0, bgy0, bgx1, bgy1), radius=radius, fill=self.uiBgColor)

                #fg
                draw.rounded_rectangle(xy=(fgx0, fgy0, fgx1, fgy1), radius=radius, fill=self.uiFgColor)
            
            if self.uiButtonHint:
                uiImg = self.draw_text(uiImg, u"\u23EE", TextPos.Y_Button, self.symbolFont, 1)
                uiImg = self.draw_text(uiImg, u"\u23ED", TextPos.B_Button, self.symbolFont, 1)
                uiImg = self.draw_text(uiImg, u"\u23EF", TextPos.A_Button, self.symbolFont, 1)
                uiImg = self.draw_text(uiImg, u"\u2139", TextPos.X_Button, self.symbolFont, 1)

            if self.uiSongInfo:
                media = self.last_track["item"]

                name, album, artists = self.get_track_info(media)

                


        return uiImg

    def draw_text(self, image, text, textPos, font, borderSize):
        textImg = Image.new("RGBA", image.size, (0,0,0,0))
        draw = ImageDraw.Draw(textImg)

        size = draw.textbbox((0,0), text, font=font)

        if textPos == TextPos.Title:
            x = (self.imageSize[0] - size[2]) / 2
            y = self.yPadding
            
        else:
            if textPos == TextPos.Y_Button or textPos == TextPos.X_Button:
                x = self.xPadding
            elif textPos == TextPos.A_Button or textPos == TextPos.B_Button:
                x = self.imageSize[0] - self.xPadding * 2 - size[2]

            if textPos == TextPos.Y_Button or textPos == TextPos.B_Button:
                y = 60 - (size[3] + 2 * borderSize) / 2
            elif textPos == TextPos.X_Button or textPos == TextPos.A_Button:
                y = 180 - (size[3] + 2 * borderSize) / 2

        draw.rounded_rectangle((x, y, x + size[2] + borderSize * 2, y + size[3] + borderSize), radius=4, fill=self.uiBgColor)
        draw.text((x + borderSize, y), text, font=font, fill=self.uiFgColor)

        return  Image.alpha_composite(image.convert('RGBA'), textImg).convert('RGB')





if __name__ == "__main__":
    ph = PirateHat()
    ph.start()