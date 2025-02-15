"""
Ticket Processing System using Producer-Consumer pattern with two processes:
  - Process A (Producer): Dynamically generates random passenger data.
    For each record, a random name is created by generate_random_name() (a random string whose length varies),
    a random age (1–90) and a random gender ("Male" or "Female") are generated.
    If age > 60, the record is given a higher priority (lower numeric value) for processing.
    The record (with generation timestamp and a sequence number) is pushed into a shared PriorityQueue.
  - Process B (Consumer): Spawns multiple consumer threads which each pull from the queue,
    compute processing time, add a completion timestamp, and write the record to category-specific files.
    Files are created with names that include the current date and hour.
  - The producer sends sentinel records so that each consumer thread terminates.

Logging and exception handling are added throughout.
"""

import logging
import time
import random
import threading
import datetime
import multiprocessing
import string
import queue

# Global constant: number of consumer threads inside Process B
CONSUMER_THREADS = 2

# Set up basic logging for all processes
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%d-%m-%Y %H:%M:%S"
)

def generate_random_name(min_len=3, max_len=10):
    """
    Generate a random string of letters with length between min_len and max_len.
    This produces names that are not pre-determined and whose length varies.
    """
    length = random.randint(min_len, max_len)
    # Use ascii_letters so names may contain both uppercase and lowercase letters.
    return ''.join(random.choices(string.ascii_letters, k=length))

def write_to_file(filename, line, file_locks):
    """
    Write a line to the given filename in an atomic (thread-safe) way.
    A lock for each filename is kept in the file_locks dict.
    """
    try:
        if filename not in file_locks:
            # Create a new lock for this file if not already present.
            file_locks[filename] = threading.Lock()
        lock = file_locks[filename]
        with lock:
            with open(filename, "a") as f:
                f.write(line)
    except Exception:
        logging.exception(f"Failed to write to file {filename}")

def consumer_thread(shared_queue, file_locks, logger, thread_id):
    """
    Worker function run by each consumer thread.
    It gets records from the shared queue, processes them, and writes them to appropriate files.
    """
    local_priority_queue = queue.PriorityQueue()
    while True:
        try:
            # Retrieve a single item from the queue
            priority, seq, record = shared_queue.get()
            # Check for sentinel (record is None)
            if record is None:
                logger.info(f"Consumer thread {thread_id} received termination signal; exiting.")
                return
            
            # Put the item into the local priority queue
            local_priority_queue.put((priority, seq, record))

            # Process items from the local priority queue
            while not local_priority_queue.empty():
                priority, seq, record = local_priority_queue.get()
                # Calculate processing time (in seconds)
                processing_time = time.time() - record["gen_time"]
                # Get completion timestamp in dd-mm-yyyy hh:mm:ss format
                completion_timestamp = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
                # For this example, set status always to "confirmed"
                status = "confirmed"
                # Build the output line
                output_line = f"{record['name']}, {record['age']}, {record['gender']}, {status}, {processing_time:.2f}, {completion_timestamp}\n"

                # Determine file names based on current date/hour
                file_suffix = datetime.datetime.now().strftime("%d-%m-%Y_%H")
                # If the record is a child, write only to ChildPassengers file.
                if record["age"] < 10:
                    filename = f"outputs/ChildPassengers_{file_suffix}.txt"
                    write_to_file(filename, output_line, file_locks)
                else:
                    # For non-child records, decide normal vs senior:
                    if record["age"] < 60:
                        filename = f"outputs/NormalCititzen_{file_suffix}.txt"
                        write_to_file(filename, output_line, file_locks)
                    else:
                        filename = f"outputs/eniorCitizen_{file_suffix}.txt"
                        write_to_file(filename, output_line, file_locks)
                    # Additionally, write by gender.
                    if record["gender"].lower() == "male":
                        filename = f"outputs/MalePassengers_{file_suffix}.txt"
                        write_to_file(filename, output_line, file_locks)
                    elif record["gender"].lower() == "female":
                        filename = f"outputs/FemalePassengers_{file_suffix}.txt"
                        write_to_file(filename, output_line, file_locks)

                logger.info(f"Consumer thread {thread_id} processed record: {record}")
        except Exception:
            logger.exception(f"Exception in consumer thread {thread_id}")

def consumer_process_main(queue, consumer_threads):
    """
    This function runs in Process B. It spawns a number of consumer threads
    that share the same queue.
    """
    logger = logging.getLogger("ConsumerProcess")
    logger.info("Consumer process started")
    file_locks = {}  # Dictionary to hold threading locks for file writes.
    threads = []
    for i in range(consumer_threads):
        t = threading.Thread(target=consumer_thread, args=(queue, file_locks, logger, i + 1))
        t.start()
        threads.append(t)
    # Wait for all consumer threads to finish.
    for t in threads:
        t.join()
    logger.info("Consumer process exiting")

def producer(queue, num_records):
    """
    This function runs in Process A. It dynamically generates random passenger records and
    pushes them into the shared priority queue.
    """
    logger = logging.getLogger("Producer")
    seq_num = 0
    genders = ["Male", "Female"]
    logger.info(f"Producer process started; producing {num_records} records.")
    for i in range(num_records):
        try:
            # Dynamically generate a random name
            name = generate_random_name()
            age = random.randint(1, 90)
            gender = random.choice(genders)
            gen_time = time.time()
            record = {
                "name": name,
                "age": age,
                "gender": gender,
                "gen_time": gen_time
            }
            # Determine priority: if age > 60 then assign high priority (0), else lower (1).
            priority = 0 if age > 60 else 1
            # Put the tuple into the queue.
            queue.put((priority, seq_num, record))
            logger.info(f"Produced record {seq_num}: {record} with priority {priority}")
            seq_num += 1
            time.sleep(random.uniform(0.1, 0.5))
        except Exception:
            logger.exception("Exception occurred in producer while generating a record")
    # Send termination signals (sentinel values) for each consumer thread.
    for _ in range(CONSUMER_THREADS):
        queue.put((100, seq_num, None))  # Use a high priority number for termination signal.
        seq_num += 1
    logger.info("Producer finished producing records")

def main():
    """
    Main entry point: Creates a shared multiprocessing.PriorityQueue,
    then spawns the producer process (Process A) and the consumer process (Process B).
    """
    logger = logging.getLogger("Main")
    logger.info("Main process started")
    num_records = 50  # Adjust as needed.
    # Create a multiprocessing.PriorityQueue (this queue is process-safe)
    priority_queue = multiprocessing.Queue()
    # Create Process A for producing records.
    prod_process = multiprocessing.Process(target=producer, args=(priority_queue, num_records))
    # Create Process B for consuming records; it will spawn consumer threads.
    cons_process = multiprocessing.Process(target=consumer_process_main, args=(priority_queue, CONSUMER_THREADS))
    # Start both processes.
    prod_process.start()
    cons_process.start()
    # Wait for both processes to finish.
    prod_process.join()
    cons_process.join()
    logger.info("Main process exiting")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Unhandled exception in main process")
