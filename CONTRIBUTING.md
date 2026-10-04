# Contributing

Thanks for helping improve Omarchy: Lunatic Fringe.

For bug reports, include your Omarchy version, what you expected, what happened, and steps to reproduce. For screensaver or bar issues, include relevant Quickshell logs; for gameplay issues, include the game launch method and any terminal errors. Remove usernames, paths, or other private information before sharing logs.

For code changes, keep campaign saves and personal configuration backward compatible. Validate the plugin and run the focused tests:

```sh
omarchy plugin validate .
/usr/bin/python -m unittest discover -s tests -v
```

Build release archives with `/usr/bin/python scripts/build_release.py`. Do not include personal saves, settings, or generated caches in commits. The player artwork was supplied separately from the MIT-licensed code; read [ASSETS.md](ASSETS.md) before changing or reusing it.
