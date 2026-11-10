# API

Functions marked with the `@api` decorator are also exposed at `/offerings/<canvas course id>/api/sudo/<name>`, for scripts. Each request needs an API key, which a course admin (an instructor or Lead TA in bCourses) makes on the course's Admin page, under API Keys. A key:

- works only in the course it was made in, and only while its owner is an admin there;
- stops working if its owner hasn't signed in to Sections for 7 days (`API_KEY_ROLE_MAX_AGE`, in seconds), because bCourses roles are only read at sign-in. Signing in again will make it work again;
- runs the function as its owner, or as the course member whose `email` the request names; never as anyone outside the course;
- can't list, create, revoke or rotate keys. Do that on the Admin page, where any admin can revoke any key in the course and rotate their own.

Only a hash of each key is stored, so a key is shown once, when it's made. Every request made with a key is logged (`sections.api_keys`) with the key, its owner, the function and who it ran as. After 10 failed key attempts in 15 minutes, a client is refused (HTTP 429) until the window passes. Clients are told apart by `X-Forwarded-For`, so behind a load balancer set `TRUSTED_PROXY_HOPS=1`; otherwise every request looks like it came from the load balancer, and 10 bad attempts from anyone lock out everyone.

## Example Request

```
curl -X POST \
  -H "Authorization: Bearer $SECTIONS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "email": "<admin>@berkeley.edu",
        "args": {
            "email": "<student>@berkeley.edu"
        }
      }' \
  "https://sections.data8.org/offerings/<canvas course id>/api/sudo/get_student_discussion_attendance"
```

`get_student_discussion_attendance` is only for admins, so `"email"` must name an admin, or be left out to run as the key's owner. Responses are `{"success": true, "data": ...}` on success. If the function itself fails (say, `"email"` names someone the function isn't allowed for, such as a non-admin here), the response is `{"success": false, "message": ...}` with HTTP 200. If the request is refused (a bad key, an `"email"` outside the course, a body that isn't JSON), it has the same shape with an HTTP error status. Check `success`, not only the status code.
