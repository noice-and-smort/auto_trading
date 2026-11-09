from util import clear_all_caches

if __name__ == "__main__":
  cleared = clear_all_caches()
  print("==========================================")
  print("NSE Cache Cleared Successfully!")
  print("==========================================")
  for app_name in cleared:
    print(f" - Emptied: {app_name}")
  print("")
  try:
    input("Press Enter to close this window...")
  except EOFError:
    pass
