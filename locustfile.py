from locust import HttpUser, task, between

class IRGTrafficSimulator(HttpUser):
    # Simulates human delay between clicks (1 to 2 seconds)
    wait_time = between(1, 2)

    # 80% of traffic spams the browse endpoint
    @task(8)
    def casual_browsing(self):
        self.client.get("/browse")

    # 20% of traffic completes a checkout order
    @task(2)
    def complete_purchase(self):
        self.client.get("/pay")