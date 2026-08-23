# Free HYPE 4H Setup Alerts -> Telegram

This checks your exact strategy logic against live HYPE data every 4 hours
and messages your Telegram bot when a setup qualifies. Runs entirely for
free using GitHub Actions - no TradingView paid plan, no server, no cost.

## One-time setup (about 10 minutes)

1. **Create a free GitHub account** at github.com if you don't have one.

2. **Create a new repository** (Repositories -> New). Name it anything,
   e.g. `hype-fib-alerts`. Set it to **Public** (required for unlimited
   free GitHub Actions minutes - Private repos also get free minutes but
   Public is simplest and this repo has no sensitive data in the code
   itself, since your token/chat ID are stored as secrets, not in files).

3. **Upload these files**, keeping the folder structure exactly as-is:
   - `telegram_alert_bot/check_setup.py`
   - `telegram_alert_bot/.github/workflows/check_setup.yml` -> this
     actually needs to live at the REPO ROOT as `.github/workflows/check_setup.yml`,
     not inside the `telegram_alert_bot` folder. Move it up one level
     when uploading, so your repo looks like:
     ```
     your-repo/
       .github/workflows/check_setup.yml
       telegram_alert_bot/check_setup.py
     ```

4. **Add your secrets.** In your repo: Settings -> Secrets and variables
   -> Actions -> New repository secret. Add two:
   - `TELEGRAM_BOT_TOKEN` = your bot token (the one from BotFather)
   - `TELEGRAM_CHAT_ID` = your chat ID (1089647477, from our earlier setup)

   Secrets are encrypted and never shown in logs - this keeps your token
   out of the code itself.

5. **Test it manually.** Go to the Actions tab -> "Check 4H Fib Setup"
   workflow -> "Run workflow" button -> Run workflow. Wait ~30 seconds,
   then check the run's logs. You should see either "No qualifying setup"
   or "Alert sent" in the output - either is a successful test.

6. **Done.** It will now run automatically every 4 hours (5 minutes after
   each 4H candle closes, UTC-aligned) and message your Telegram the
   moment a setup qualifies, with entry/stop/target included.

## Keeping it in sync with your strategy

If you ever change the .pine strategy's inputs (minMovePct, fibEntry,
fibExtension, volMultiplier, atrMultiplier), update the matching
constants at the top of `check_setup.py` too, so the two stay identical.

## Notes

- Uses Binance's public Futures API (no API key needed) for HYPEUSDT
  4H candles - free, no account required.
- `state.json` tracks which candle was last alerted on, so you won't get
  duplicate messages if the workflow happens to run twice near the same
  candle close.
- GitHub free-tier scheduled Actions can occasionally run a few minutes
  late during high platform load - this won't cause missed or duplicate
  alerts, just an occasional short delay.
