import httpx
import asyncio
import uuid
from app.middleware.auth import create_access_token


BASE_URL = "http://localhost:8000"


async def safe_request(resp: httpx.Response, step: str):
    """Print response + fail loudly if error"""
    print(f"{step}: {resp.status_code}")

    try:
        print(resp.json())
    except Exception:
        print(resp.text)

    resp.raise_for_status()


async def main():

    async with httpx.AsyncClient(timeout=30.0) as client:

        # ---------------------------------------------------
        print("\n1️⃣ Checking Health...")
        resp = await client.get(f"{BASE_URL}/health")
        await safe_request(resp, "Health")

        # ---------------------------------------------------
        print("\n2️⃣ Registering Driver...")

        driver_payload = {
            "name": "Test Driver",
            "phone": f"+91{uuid.uuid4().int % 10000000000:010d}",
            "tier": "standard",
        }

        resp = await client.post(f"{BASE_URL}/v1/drivers", json=driver_payload)
        await safe_request(resp, "Register Driver")

        driver_data = resp.json()
        driver_id = (
            driver_data.get("id")
            or driver_data.get("driver_id")
            or driver_data.get("data", {}).get("id")
        )

        if not driver_id:
            raise Exception("Driver ID not found in response")

        # ---------------------------------------------------
        print("\n3️⃣ Generating Tokens...")

        driver_token = create_access_token({"sub": str(driver_id)})
        rider_id = str(uuid.uuid4())
        rider_token = create_access_token({"sub": rider_id})

        driver_headers = {"Authorization": f"Bearer {driver_token}"}
        rider_headers = {"Authorization": f"Bearer {rider_token}"}

        # ---------------------------------------------------
        print("\n4️⃣ Driver goes online...")
        resp = await client.patch(
            f"{BASE_URL}/v1/drivers/{driver_id}/status",
            params={"new_status": "available"},
            headers=driver_headers,
        )
        await safe_request(resp, "Driver Online")

        # ---------------------------------------------------
        print("\n5️⃣ Driver sends location...")
        resp = await client.post(
            f"{BASE_URL}/v1/drivers/{driver_id}/location",
            json={"lat": 12.9716, "lng": 77.5946},
            headers=driver_headers,
        )
        await safe_request(resp, "Send Location")

        # ---------------------------------------------------
        print("\n6️⃣ Rider creates ride...")

        ride_payload = {
            "pickup_lat": 12.9716,
            "pickup_lng": 77.5946,
            "dest_lat": 13.0827,
            "dest_lng": 80.2707,
            "tier": "standard",
            "payment_method": "card",
        }

        rider_headers_with_idem = {
            **rider_headers,
            "Idempotency-Key": str(uuid.uuid4()),
        }

        resp = await client.post(
            f"{BASE_URL}/v1/rides",
            json=ride_payload,
            headers=rider_headers_with_idem,
        )
        await safe_request(resp, "Create Ride")

        ride_data = resp.json()
        ride_id = (
            ride_data.get("id")
            or ride_data.get("ride_id")
            or ride_data.get("data", {}).get("id")
        )

        if not ride_id:
            raise Exception("Ride ID not found")

        # ---------------------------------------------------
        print("\n7️⃣ Driver accepts ride...")
        resp = await client.post(
            f"{BASE_URL}/v1/drivers/{driver_id}/accept",
            json={"ride_id": ride_id},
            headers=driver_headers,
        )
        await safe_request(resp, "Accept Ride")

        res_json = resp.json()
        trip_id = res_json.get("trip_id") or ride_id

        # ---------------------------------------------------
        print("\n8️⃣ Ending Trip...")
        resp = await client.post(
            f"{BASE_URL}/v1/trips/{trip_id}/end",
            json={"final_lat": 13.0827, "final_lng": 80.2707},
            headers=driver_headers,
        )
        await safe_request(resp, "End Trip")

        # ---------------------------------------------------
        print("\n9️⃣ Rider pays...")
        resp = await client.post(
            f"{BASE_URL}/v1/payments",
            headers={
                **rider_headers,
                "Idempotency-Key": str(uuid.uuid4()),
            },
            json={
                "trip_id": trip_id,
                "payment_method": "card",
                "amount": 480.00,
            },
        )
        await safe_request(resp, "Payment")

        print("\n✅ FLOW COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    asyncio.run(main())