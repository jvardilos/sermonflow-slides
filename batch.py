from slidegen import batch_create

verses = [
    (
        "There is no fear in love, but perfect love casts out fear. For fear has to do with punishment, and whoever fears has not been perfected in love.",
        "1 John 4:18 ESV",
    ),
    (
        "In the beginning was the Word, and the Word was with God, and the Word was God",
        "John 1:1 ESV",
    ),
]
batch_create(verses, output_dir="./slides")
