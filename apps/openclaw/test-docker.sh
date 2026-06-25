docker exec -it openclaw-sandbox python3 -c "
import feedparser
import jsonschema
print(feedparser.__version__)
print(jsonschema.__version__)
"
