from slidegen import batch_create

verses = [
    ("For God so loved the world...", "John 3:16 ESV"),
    ("In the beginning was the Word...", "John 1:1 ESV"),
]
batch_create(verses, output_dir="./slides")
