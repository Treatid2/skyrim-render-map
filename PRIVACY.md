# Privacy

The repository does not use hardware-derived identity or background telemetry.

A future capture exporter may create a random, repository-specific installation
identifier to correlate repeated measurements. It must not derive that value
from a Windows SID, username, machine name, Steam account, serial number, MAC
address, IP address, or hardware identifier. Publication must be opt-in and the
identifier must be resettable.

CPU and GPU model combinations can themselves be identifying in a small
population. Performance exporters must preview every public field and obtain a
separate submission confirmation after collection.

Ordinary submissions must not contain:

- absolute filesystem paths;
- personal or account identifiers;
- process environment dumps or unrestricted command lines;
- network identifiers;
- credentials or authentication material;
- screenshots, save files, crash dumps, or memory dumps unless a dedicated
  reviewed evidence policy explicitly permits them.

The automated check can detect only common structural mistakes. Contributors
and reviewers remain responsible for examining the final public bundle.
