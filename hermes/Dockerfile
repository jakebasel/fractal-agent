# Hermes Agent (Nous Research) as the trade reviewer. Official image, entrypoint untouched
# (s6 must stay PID 1). Our seed files are copied to /opt/seed; loop.sh seeds /opt/data
# (the persistent volume) on first run, then reviews settled trades every REVIEW_EVERY_MIN.
FROM nousresearch/hermes-agent:latest
COPY seed/ /opt/seed/
# HERMES_OPENROUTER_CACHE: OpenRouter prompt/response caching (DeepSeek and Gemini both cache
# repeated prefixes, so the system prompt + skill + memory are paid once, not per turn)
ENV HERMES_MAX_ITERATIONS=30 HERMES_API_TIMEOUT=300 HERMES_QUIET=true REVIEW_EVERY_MIN=20 \
    HERMES_OPENROUTER_CACHE=1 HERMES_OPENROUTER_CACHE_TTL=3600
# bare-executable pass-through: the image dispatcher runs this instead of the gateway
CMD ["bash", "/opt/seed/loop.sh"]
