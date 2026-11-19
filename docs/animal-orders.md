# Animal orders

Orders use the application's Jinja templates and native HTML forms. Python
order objects are passed directly to the templates. Selection changes and
filters reload the page; successful submissions and reviews redirect with
HTTP 303 before the updated page is rendered. No order data is injected by
JavaScript.

| Method | Route | Result |
| --- | --- | --- |
| GET | `/orders` | Order form and visible orders, rendered as HTML. |
| POST | `/orders` | Validate and store an order, then redirect to the orders page. |
| GET | `/orders/<uuid>` | An individual visible order, rendered as HTML. |
| POST | `/orders/<uuid>/status` | Approve or reject a pending order, then redirect. |

All routes require login. Regular users see their own orders; Paw Control
members can see and review all orders, independently of admin status or licence
membership. Historical orders remain visible after account or licence changes.

The selection form sends `licence=protocol/A` and
`order_type=by_id|by_data` as GET parameters to load the appropriate line choices
and input fields. The filter form uses `user=<requester email>` and
`status=pending|approved|rejected`. Both forms preserve the other selection.

Submission uses POST form fields: licence, line, order type, delivery date and
comment, plus either IDs or sex/age/amount. IDs accept comma- or
whitespace-separated text, or repeated form fields. Delivery must be at least
three calendar days ahead. The server derives requester, UUID, creation time
and pending status. Expected validation errors render the form again with its
values and error message; successful submissions redirect to avoid duplicate
orders on refresh.

Capacity is the configured allowance minus all assigned animals for the
protocol/subprotocol and line, matching the protocol settings page. Pending and
approved orders do not reserve capacity. Zero and unset allowances block
submission.

Only pending orders can be approved or rejected. Approval rechecks current
licence, line and capacity without reapplying the submission lead time.
Rejection remains possible after configuration changes. A conditional database
update prevents competing reviews from overwriting each other, and failed
writes roll back through the shared error handler.
