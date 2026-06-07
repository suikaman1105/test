#!/bin/bash
# 毎日9時にスクレイピングを自動実行するcronジョブを登録する

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(which python3 || which python)"
LOG="$SCRIPT_DIR/scrape.log"

CRON_JOB="0 9 * * * cd $SCRIPT_DIR && $PYTHON $SCRIPT_DIR/scrape_suumo.py >> $LOG 2>&1"

# 既存のcronに追加（重複チェックあり）
(crontab -l 2>/dev/null | grep -v "scrape_suumo.py"; echo "$CRON_JOB") | crontab -

echo "cronジョブを登録しました:"
echo "  $CRON_JOB"
echo ""
echo "毎朝9:00に自動でスクレイピングが実行されます。"
echo "ログ: $LOG"
echo ""
echo "確認: crontab -l"
echo "削除: crontab -e で該当行を削除"
