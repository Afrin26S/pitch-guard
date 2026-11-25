# Afrin: your Hinglish review (15 minutes, high value)

I wrote the synthetic calls in `data/calls.yaml`. You are the native speaker, so please:

1. **Naturalness pass.** Read these lines aloud. If a real bot or caller would never say it that way, rewrite it in the YAML:
   - t01 turn 4 and 8 (premium / claim ratio explanation)
   - t02 turn 4 (guaranteed returns pitch)
   - t03 turn 6 (fake urgency)
   - l02 turn 4 (approval promise)
   - c02 turn 6 (threat)
   - c01 turn 4 (hardship / payment options)
2. **Add the phrases I missed.** Open `data/rulebook.yaml`. For GUARANTEE, URGENCY, PRESSURE and THREAT, add 3-5 phrases per rule that
   real sales/collection agents use in Hinglish (different spellings: nahi / nahin / nhi, hai / hain, karwa dijiye ...).
3. **Write 3-5 held-out calls WITHOUT looking at the rulebook** (one clean, a few with violations you invent), add them to `calls.yaml`
   with labels, then run `python -m pitchguard.evaluate --mode rules`. Whatever it misses is the honest number to report.
4. Check the two fictional product sheets in `data/products.yaml` read like plausible insurance / loan terms to you.
