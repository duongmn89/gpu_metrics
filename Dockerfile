FROM ubuntu:22.04

RUN apt-get update && apt install -y python3-pip wget libglib2.0-0 --no-install-recommends

ARG NSYS_URL=https://developer.download.nvidia.com/devtools/nsight-systems/
ARG NSYS_PKG=NsightSystems-linux-cli-public-2025.3.1.90-3582212.deb

RUN wget ${NSYS_URL}${NSYS_PKG} && dpkg -i $NSYS_PKG && rm $NSYS_PKG
RUN apt-get autoremove
RUN rm -rf /var/lib/apt/lists/*


# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY * ./
RUN pip install --no-cache-dir -r requirements.txt

# Set default environment variables
ENV COMMAND="echo"
ENV OUTPUT="report"
ENV METRIC="SMs Active,GR Active"
ENV PORT=9401
ENV INTERVAL=60

# Command to run the script
CMD ["python3", "gpu_metrics.py"]
