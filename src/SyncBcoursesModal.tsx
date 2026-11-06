import { useCallback, useContext, useState } from "react";
import Button from "react-bootstrap/Button";
import Modal from "react-bootstrap/Modal";
import Spinner from "react-bootstrap/Spinner";
import MessageContext from "./MessageContext";
import useAPI from "./useAPI";
import useStateAPI from "./useStateAPI";

type Props = {
  show: boolean;
  onClose: () => void;
};

type Preview = {
  added: Array<string>;
  removed: Array<string>;
  skipped: Array<string>;
  no_email: Array<string>;
};

function EmailList({
  title,
  emails,
}: {
  title: string;
  emails: Array<string>;
}) {
  if (emails.length === 0) {
    return null;
  }
  return (
    <details className="mb-2">
      <summary>{title}</summary>
      <ul className="mb-0">
        {emails.map((email, i) => (
          // Names, unlike emails, can repeat.
          <li key={`${i}-${email}`}>{email}</li>
        ))}
      </ul>
    </details>
  );
}

export default function SyncBcoursesModal({ show, onClose }: Props) {
  const { pushMessage } = useContext(MessageContext);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const fetchPreview = useAPI("preview_bcourses_sync", setPreview);
  const sync = useStateAPI(
    "sync_bcourses",
    useCallback(
      ({ custom }: { custom: { message?: string | null } }) =>
        pushMessage(custom.message ?? "Synced.", "success"),
      [pushMessage],
    ),
  );

  const loadPreview = () => {
    setPreview(null);
    setLoading(true);
    // A failure shows its error at the top of the page.
    fetchPreview().finally(() => setLoading(false));
  };

  const onSync = async () => {
    setSyncing(true);
    await sync();
    setSyncing(false);
    onClose();
  };

  const unchanged =
    preview != null &&
    preview.added.length === 0 &&
    preview.removed.length === 0;

  return (
    <Modal show={show} onShow={loadPreview} onHide={onClose}>
      <Modal.Header closeButton>
        <Modal.Title>Sync bCourses</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p>
          Makes this course&rsquo;s students match its bCourses roster,
          including students who haven&rsquo;t accepted their invitation yet.
          Students no longer on the roster are removed from the course and its
          sections; their attendance records are kept. Staff aren&rsquo;t
          changed. This may take a minute to load.
        </p>
        {loading ? (
          <div role="status" aria-live="polite">
            <Spinner animation="border" size="sm" className="me-2" />
            Checking bCourses&hellip;
          </div>
        ) : preview == null ? (
          <p className="mb-0">
            Couldn&rsquo;t check bCourses. See the error at the top of the page.
          </p>
        ) : (
          <>
            <p>
              {unchanged
                ? "This course's students already match bCourses."
                : `This will add ${preview.added.length} and remove ${preview.removed.length} students.`}
            </p>
            <EmailList
              title={`Students to add (${preview.added.length})`}
              emails={preview.added}
            />
            <EmailList
              title={`Students to remove (${preview.removed.length})`}
              emails={preview.removed}
            />
            {preview.skipped.length > 0 && (
              <>
                <p className="mt-3 mb-1">
                  {preview.skipped.length} students on the bCourses roster
                  won&rsquo;t be added. Their email already belongs to someone
                  in Sections with a different bCourses account, so Sections
                  can&rsquo;t tell whether they&rsquo;re the same person.
                  Contact the Sections maintainers to sort these out.
                </p>
                <EmailList
                  title={`Students not added (${preview.skipped.length})`}
                  emails={preview.skipped}
                />
              </>
            )}
            {preview.no_email.length > 0 && (
              <>
                <p className="mt-3 mb-1">
                  {preview.no_email.length} students on the bCourses roster
                  won&rsquo;t be added because bCourses didn&rsquo;t share their
                  email, which Sections needs for everyone.
                </p>
                <EmailList
                  title={`Students without an email (${preview.no_email.length})`}
                  emails={preview.no_email}
                />
              </>
            )}
          </>
        )}
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="danger"
          onClick={onSync}
          disabled={preview == null || unchanged || syncing}
        >
          {syncing ? "Syncing…" : "Sync"}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
