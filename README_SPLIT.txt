# Standalone Player split

Gateway machine (GATEWAY_HOST)
- EXE: FLVTokenGateway.exe
- config: .env
- build spec: existing FLVTokenGateway_v04_sslfix.spec
- only Gateway knows Origin ORIGIN_HOST

Player machine (CLIENT_HOST)
- EXE: FLVTokenPlayer.exe
- config: player_config.json
- build spec: FLVTokenPlayer.spec
- Player config contains Gateway GATEWAY_HOST only, never Origin ORIGIN_HOST

Build Player:
  python -m PyInstaller --clean --noconfirm FLVTokenPlayer.spec

Source smoke test:
  python standalone_player/server.py
