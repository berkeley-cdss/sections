import moment from "moment";
import { useCallback, useEffect, useState } from "react";
import Alert from "react-bootstrap/Alert";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import InputGroup from "react-bootstrap/InputGroup";
import Table from "react-bootstrap/Table";
import COURSE_BASE from "./coursePath";
import useAPI from "./useAPI";

type ApiKey = {
  id: number;
  name: string;
  hint: string;
  owner: { name: string; email: string };
  isMine: boolean;
  createdAt: number;
  lastUsedAt: number | null;
};

type NewKey = { key: string; name: string; keys: Array<ApiKey> };

function formatTime(seconds: number | null) {
  return seconds == null ? "Never" : moment.unix(seconds).format("MMM D, YYYY h:mm a");
}

// Course admins' keys for this course's API (/api/sudo/<name>), see docs/api.md.
export default function ApiKeysTab() {
  const [keys, setKeys] = useState<Array<ApiKey> | null>(null);
  const [name, setName] = useState("");
  // Shown once, right after it's made: the server keeps only a hash.
  const [newKey, setNewKey] = useState<{ name: string; key: string } | null>(null);

  const listKeys = useAPI("list_api_keys", setKeys);
  const showNewKey = useCallback((data: NewKey) => {
    setKeys(data.keys);
    setNewKey({ name: data.name, key: data.key });
    setName("");
  }, []);
  const createKey = useAPI("create_api_key", showNewKey);
  const revokeKey = useAPI("revoke_api_key", setKeys);
  const rotateKey = useAPI("rotate_api_key", showNewKey);

  useEffect(() => {
    listKeys();
  }, [listKeys]);

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    setNewKey(null);
    await createKey({ name });
  };

  return (
    <div className="mt-3">
      <p>
        An API key lets a script call this course&rsquo;s Sections API as you, or as anyone in this
        course. It works only in this course, only while you&rsquo;re an admin here in bCourses, and
        only if you&rsquo;ve signed in to Sections in the last week. Every request is logged with the
        key that made it. Treat a key like a password; if one leaks, revoke it.
      </p>
      <p>
        Send it as <code>Authorization: Bearer &lt;key&gt;</code> to{" "}
        <code>
          {window.location.origin}
          {COURSE_BASE}/api/sudo/&lt;name&gt;
        </code>
        .
      </p>

      {newKey != null && (
        <Alert variant="success" onClose={() => setNewKey(null)} dismissible>
          <p>
            Your new key for &ldquo;{newKey.name}&rdquo;. Copy it now: it won&rsquo;t be shown again.
          </p>
          <InputGroup>
            <Form.Control readOnly value={newKey.key} aria-label="New API key" className="font-monospace" />
            <Button variant="outline-secondary" onClick={() => navigator.clipboard.writeText(newKey.key)}>
              Copy
            </Button>
          </InputGroup>
        </Alert>
      )}

      <Form onSubmit={create} className="mb-3">
        <Form.Label htmlFor="api-key-name">New key</Form.Label>
        <InputGroup>
          <Form.Control
            id="api-key-name"
            placeholder="What it's for, e.g. Gradescope attendance sync"
            value={name}
            maxLength={255}
            onChange={(e) => setName(e.target.value)}
          />
          <Button type="submit" disabled={!name.trim()}>
            Create key
          </Button>
        </InputGroup>
      </Form>

      {keys == null ? null : keys.length === 0 ? (
        <p>No one has an API key for this course.</p>
      ) : (
        <Table striped responsive>
          <thead>
            <tr>
              <th>Name</th>
              <th>Key</th>
              <th>Owner</th>
              <th>Created</th>
              <th>Last used</th>
              <th>
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => (
              <tr key={key.id}>
                <td>{key.name}</td>
                <td className="font-monospace">…{key.hint}</td>
                <td>{key.isMine ? "You" : `${key.owner.name} (${key.owner.email})`}</td>
                <td>{formatTime(key.createdAt)}</td>
                <td>{formatTime(key.lastUsedAt)}</td>
                <td className="text-nowrap">
                  {key.isMine && (
                    <>
                      <Button
                        size="sm"
                        variant="outline-secondary"
                        aria-label={`Rotate ${key.name}`}
                        onClick={() => {
                          setNewKey(null);
                          rotateKey({ key_id: key.id });
                        }}
                      >
                        Rotate
                      </Button>{" "}
                    </>
                  )}
                  <Button
                    size="sm"
                    variant="outline-danger"
                    aria-label={`Revoke ${key.name}`}
                    onClick={() => {
                      if (window.confirm(`Revoke "${key.name}"? Scripts using it will stop working.`)) {
                        revokeKey({ key_id: key.id });
                      }
                    }}
                  >
                    Revoke
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}
