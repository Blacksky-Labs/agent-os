# First-launch slideshow images

These images play full-screen during the **first launch**, while Skipper downloads
the on-device model (a one-time, multi-minute wait). `SlideshowView.swift` reads
this folder at runtime and shows each image full-screen, in filename order, each
paired with one of the built-in quotes (the quotes **cycle** — there are 5, the
images don't have to match that count).

**Currently:** 53 images, cycling 5 quotes.

## Swapping in your own images

Just replace the files here. There's no code to touch and no Xcode asset catalog
to manage — this folder ships into the app as a **folder reference**
(`Contents/Resources/Slides`), so whatever is in here is what plays.

- **How many:** any number. Quotes cycle to cover them all.
- **Order:** alphabetical by filename. Rename if you want a specific sequence.
- **Formats:** `.png`, `.jpg/.jpeg`, `.heic`, `.tiff`, `.gif`, `.bmp`.
- **Size:** landscape, ~1600×1000 or larger. Shown *aspect-fill* (cropped to cover
  the window), so keep the important part near the center.
- **Tone:** darker images read best — white quote text sits over the lower third,
  with a built-in top/bottom scrim for legibility.

## The quotes

The 5 captions live in `SlideshowView.swift` (`Quote.all`). Edit that array to change
them; they cycle across the images (image *N* shows quote *N mod 5*).

## If the folder is empty

The slideshow still runs — each slide falls back to an on-brand gradient backdrop,
so the first-launch experience is never blank.
