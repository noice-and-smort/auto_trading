import asyncio
import logging
import os
import shutil
import warnings
from appdirs import user_cache_dir
from nse_history import NSEHistory
from script import run, write_to_file
from telegram import Bot, Update
from telegram.ext import Application, CallbackContext, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

warnings.filterwarnings("ignore")

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)

# --- Configuration ---
from util import load_dotenv
load_dotenv(".env")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")


# --- Handler Functions ---

default_message = (
    f"Hi Papa,\n\n\+ Type *Go*, if you want to get the file with the latest"
    f" data\.\n\n\+ Type *Stocks*, if you want to get the list of"
    f" stocks\.\n\n\+ Type *Empty*, if you want to empty the cache\.\n\n\+"
    f" *Upload* the new stocks file using the icon, if you want to update the"
    f" list of stocks\.\n\nIf the bot does not seem to be responding to"
    f" messages, wait for some time\. It restarts every 1 hr\.\n\n"
)
stocks_file_name = "data/stocks"
latest_out_file = "output/latest.csv"


async def start(update: Update, context: CallbackContext) -> None:
  """Sends an acknowledgment that the message was received."""
  await update.message.reply_markdown_v2(default_message)


async def handle_file(update: Update, context: CallbackContext) -> None:
  """Handles received documents.

  Specifically looks for 'stocks' file to save.
  """
  message = update.message
  user = update.effective_user

  # This function is called for documents due to `filters.Document.ALL`.
  if not message.document:
    logger.error(
        f"handle_file was called for user {user.id} without a document, despite"
        f" document filter. Message: {message}"
    )
    await message.reply_text("Please upload the right stocks file.")
    return

  original_file_name = message.document.file_name
  if not original_file_name:
    logger.warning(
        f"Received document from {user.first_name} ({user.id}) is missing a"
        " filename."
    )
    await update.message.reply_markdown_v2(default_message)
    return

  logger.info(
      f"User {user.first_name} ({user.id}) sent a document:"
      f" '{original_file_name}'"
  )

  # Check if the base name of the file is 'stocks' (case-insensitive)
  base_name, extension = os.path.splitext(original_file_name)

  if base_name.lower() == stocks_file_name:
    try:
      file_id = message.document.file_id
      telegram_file_obj = await context.bot.get_file(file_id)
      await telegram_file_obj.download_to_drive(custom_path=stocks_file_name)
      reply_text = f"The list of stocks has been updated successfully."
      await message.reply_text(reply_text)
      logger.info(
          f"Stocks file '{original_file_name}' from user"
          f" {user.first_name} saved."
      )
      await update.message.reply_markdown_v2(default_message)

    except Exception as e:
      logger.error(
          f"Failed to download or save 'stocks' file '{original_file_name}'"
          f" from user {user.first_name}. Error: {e}",
          exc_info=True,
      )
      await message.reply_text(
          "There was an error processing your stocks file"
          f" '{original_file_name}'. Please try again."
      )
      await update.message.reply_markdown_v2(default_message)
  else:
    # This is a document, but not named 'stocks'
    reply_text = (
        f"I received your document: '{original_file_name}', but not taking any"
        " action.\n\nIf you meant to update the stocks list, please ensure the"
        " file is named 'stocks' (e.g., 'stocks.csv', 'stocks.txt')."
    )
    await message.reply_text(reply_text)
    await update.message.reply_markdown_v2(default_message)
    logger.info(
        f"Received document '{original_file_name}' from user {user.first_name},"
        " not a 'stocks' file."
    )


async def handle_text_message(update: Update, context: CallbackContext) -> None:
  """Handles text messages."""
  message_text = update.message.text
  user = update.effective_user

  keyword = None
  if not message_text:
    return
  if "go" in message_text.lower():  # Check for 'go' keyword
    keyword = "go"
  elif "stocks" in message_text.lower():  # Check for 'stocks' keyword
    keyword = "stocks"
  elif "test" in message_text.lower():  # Check for 'test' keyword
    keyword = "test"
  elif "empty" in message_text.lower():  # Check for 'empty' keyword
    keyword = "empty"

  if keyword == "go" or keyword == "test":  # Check for 'go' or 'test' keyword
    logger.info(f"User {user.first_name} ({user.id}) requested stocks data.")
    if os.path.exists(stocks_file_name):
      await update.message.reply_text("Staring to fetch the latest stock data.")
      try:
        stock_data_list = []
        stock_names = []
        finished_stock_names = []
        with open(stocks_file_name, "r") as f_document:
          for line in f_document:
            if line.strip():
              stock_names.append(line.strip())
        num_stocks = len(stock_names)
        if keyword == "test":
          num_stocks = min(num_stocks, 10)
        for attempt in range(1, 6):
          finished_stock_names, stock_data_list = (
              await _fetch_stock_data_attempt(
                  stock_names,
                  finished_stock_names,
                  stock_data_list,
                  num_stocks,
                  update,
                  30.0,
              )
          )
          if len(finished_stock_names) == num_stocks:
            break
        unfinished_stock_names = [
            stock_name
            for stock_name in stock_names
            if stock_name not in finished_stock_names
        ]
        if len(finished_stock_names) != num_stocks:
          logger.error(
              f"Failed to fetch data for stocks: {unfinished_stock_names}"
          )
          await update.message.reply_text(
              "Fetched data for"
              f" {len(finished_stock_names)}/{num_stocks} stocks in total."
              f" Failed to fetch data for stocks: {unfinished_stock_names}. Try"
              " running again to get data for the remaining stocks."
          )
        else:
          await update.message.reply_text(
              "Fetched data for"
              f" {len(finished_stock_names)}/{num_stocks} stocks in total."
          )

        write_to_file(stock_data_list, latest_out_file)
        with open(latest_out_file, "rb") as f_document:
          await update.message.reply_document(
              document=f_document, filename=latest_out_file
          )
        logger.info(f"Sent stocks data to user {user.first_name} ({user.id}).")
      except Exception as e:
        logger.error(f"Error fetching stock data: {e}", exc_info=True)
        await update.message.reply_text(
            "Sorry, there was an error fetching the latest stock data."
        )
    else:
      await update.message.reply_text(
          "The stocks data file has not been uploaded yet. "
          "Please upload a file named 'stocks' (e.g., 'stocks.csv') to set it."
      )
    await update.message.reply_markdown_v2(default_message)

  elif keyword == "stocks":  # Check for 'stocks' keyword
    logger.info(
        f"User {user.first_name} ({user.id}) requested the stocks file."
    )
    if os.path.exists(stocks_file_name):
      try:
        # Send the stored data file, using the retrieved (or default) display filename
        with open(stocks_file_name, "rb") as f_document:
          await update.message.reply_document(
              document=f_document, filename=stocks_file_name
          )
        logger.info(
            f"Sent stocks file (content from '{stocks_file_name}') to user"
            f" {user.first_name} ({user.id})."
        )
      except Exception as e:
        logger.error(f"Error sending stocks file: {e}", exc_info=True)
        await update.message.reply_text(
            "Sorry, there was an error trying to send the stocks file."
        )
    else:
      await update.message.reply_text(
          "The stocks data file has not been uploaded yet. "
          "Please upload a file named 'stocks' (e.g., 'stocks.csv') to set it."
      )
    await update.message.reply_markdown_v2(default_message)

  elif keyword == "empty":  # Check for 'empty' keyword
    logger.info(
        f"User {user.first_name} ({user.id}) requested to empty the cache."
    )
    try:
      app_names = [
          "nsehistory-derivatives",
          "nsehistory-stock",
          "nsehistory-option_chain",
          "nsehistory-deliverables",
      ]
      for app_name in app_names:
        cache_path = user_cache_dir(app_name, app_name)
        if not os.path.isdir(cache_path):
          logger.error(f"Error: '{cache_path}' is not a valid directory.")
          await update.message.reply_text(
              "Sorry, there was an error emptying the cache."
          )
          await update.message.reply_markdown_v2(default_message)
          return
        for filename in os.listdir(cache_path):
          file_path = os.path.join(cache_path, filename)
          try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
              os.unlink(file_path)  # Remove file or symbolic link
            elif os.path.isdir(file_path):
              shutil.rmtree(file_path)  # Remove directory and all its contents
          except Exception as e:
            logger.error(f"Error emptying directory: {e}", exc_info=True)
        logger.info(f"Cache emptied for {cache_path}.")
        await update.message.reply_text(f"Cache emptied for {app_name}.")
    except Exception as e:
      logger.error(f"Error emptying cache: {e}", exc_info=True)
      await update.message.reply_text(
          "Sorry, there was an error emptying the cache."
      )
    await update.message.reply_markdown_v2(default_message)


async def _fetch_stock_data_attempt(
    stock_names,
    finished_stock_names,
    stock_data_list,
    num_stocks,
    update,
    timeout,
):
  h = NSEHistory()
  for i in range(num_stocks):
    if stock_names[i] in finished_stock_names:
      continue
    try:
      stock_name, stock_data = await asyncio.wait_for(
          asyncio.to_thread(run, h, stock_names[i]), timeout=timeout
      )
      if stock_name in finished_stock_names:
        continue
      if stock_data:
        finished_stock_names.append(stock_name)
        stock_data_list.append((stock_name, stock_data))
        num_finished_stocks = len(finished_stock_names)
        if num_finished_stocks % 5 == 0:
          await update.message.reply_text(
              f"Fetched data for {num_finished_stocks}/{num_stocks} stocks."
          )
    except asyncio.TimeoutError:
      logger.error(
          f"Timeout in fetching stock data for {stock_names[i]}. (Timeout:"
          f" {timeout}s)",
          exc_info=True,
      )
      h = NSEHistory()
    except Exception as e:
      logger.error(
          f"Error fetching stock data for {stock_names[i]}: {e}", exc_info=True
      )
      h = NSEHistory()
  return finished_stock_names, stock_data_list


def main() -> None:
  """Start the bot."""
  if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
    logger.error(
        "IMPORTANT: Please ensure your actual bot token is correctly set."
    )
    # return

  # Configure custom HTTPX request settings for timeouts
  custom_httpx_request = HTTPXRequest(
      connect_timeout=10.0,  # Timeout for establishing a connection (seconds)
      read_timeout=30.0,  # Timeout for reading data from the server (seconds)
      write_timeout=30.0,  # Timeout for writing data to the server (seconds)
  )

  # Create a Bot instance with the custom request settings
  bot_instance = Bot(token=TELEGRAM_BOT_TOKEN, request=custom_httpx_request)

  # Build the application with the pre-configured bot instance
  application = Application.builder().bot(bot_instance).build()

  application.add_handler(CommandHandler("start", start))

  attachment_filters = filters.Document.ALL
  application.add_handler(MessageHandler(attachment_filters, handle_file))
  application.add_handler(
      MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
  )

  logger.info("Starting bot polling...")
  application.run_polling(
      timeout=30
  )  # You can also keep a polling timeout here
  logger.info("Bot stopped (should not be reached if run_polling is active).")


if __name__ == "__main__":
  main()
