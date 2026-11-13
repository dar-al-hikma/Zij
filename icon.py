from PIL import Image

# app_icon_source.png is a 2048px reduction of the owner's 4096px master
# (abbasid-astrology-icon-master-4096.png, kept outside the repo); nothing
# below needs more than the 1024px .icns slot.
img = Image.open("app_icon_source.png")
icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save("app_icon.ico", format="ICO", sizes=icon_sizes)

# .icns for the macOS .app bundle (build.spec's BUNDLE(icon=...)). Pillow
# downsamples the full-res source to fill every size Apple expects, up to
# the 1024px (@2x) slot.
img.convert("RGBA").save("app_icon.icns", format="ICNS")

# The opening page's icon (opening.py): the owner's lapis emblem, kept
# unchanged as app_icon_opening_source.png (the program's own icon above is not
# touched), reduced to the one size the page draws it at twice over: 256 px a
# side, shown at 128.
with Image.open("app_icon_opening_source.png") as emblem:
    emblem.convert("RGBA").resize((256, 256), Image.LANCZOS).save("app_icon_opening.png", optimize=True)
