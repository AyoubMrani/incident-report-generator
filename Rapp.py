"""Legacy launcher for the modular NRI incident chatbot.

Primary code now lives in the `incident_chatbot` package.
Keep this file as a thin compatibility entrypoint only.
"""

from incident_chatbot.main import main


if __name__ == "__main__":
    main()
