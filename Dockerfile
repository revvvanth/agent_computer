FROM kareos-research-openbot:4773ef686654
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/* && useradd -m -u 1001 researcher && mkdir -p /lab /lab-data /profiles /workspace && chown -R researcher:researcher /profiles /workspace /lab-data
COPY portal.py calculator.py /lab/
COPY start.sh /lab/start.sh
USER researcher
ENV EGRESS_POLICY_REQUIRED=0 COMPUTER_BROWSER_MODE=headless
CMD ["sh", "/lab/start.sh"]
