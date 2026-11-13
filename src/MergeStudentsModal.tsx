import { useCallback, useContext, useRef, useState } from "react";
import Button from "react-bootstrap/Button";
import Form from "react-bootstrap/Form";
import Modal from "react-bootstrap/Modal";
import MessageContext from "./MessageContext";
import useStateAPI from "./useStateAPI";

type Props = {
  show: boolean;
  onClose: () => void;
};

export default function MergeStudentsModal({ show, onClose }: Props) {
  const { pushMessage } = useContext(MessageContext);
  const [oldEmail, setOldEmail] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [merging, setMerging] = useState(false);
  // Clear the inputs whenever the modal closes.
  const [prevShow, setPrevShow] = useState(show);
  if (show !== prevShow) {
    setPrevShow(show);
    if (!show) {
      setOldEmail("");
      setNewEmail("");
    }
  }

  // Set by the success callback, so the modal stays open after a failure,
  // which has already shown its error at the top of the page.
  const merged = useRef(false);
  const merge = useStateAPI(
    "merge_students",
    useCallback(
      ({ custom }: { custom: { message?: string | null } }) => {
        merged.current = true;
        pushMessage(custom.message ?? "Merged.", "success");
      },
      [pushMessage],
    ),
  );

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    merged.current = false;
    setMerging(true);
    await merge({ old_email: oldEmail, new_email: newEmail });
    setMerging(false);
    if (merged.current) {
      onClose();
    }
  };

  return (
    <Modal show={show} onHide={onClose}>
      <Form onSubmit={onSubmit}>
        <Modal.Header closeButton>
          <Modal.Title>Merge Students</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          <p>
            For a student whose email changed before they first signed in to
            Sections: they were added under their old email (by a spreadsheet
            import or by staff), and signing in added them again under their new
            one. Merging moves the old email&rsquo;s sections and attendance to
            the new one and deletes the old one.
          </p>
          <p>
            Only an email no one has signed in with can be merged. Students who
            have signed in get their new email the next time they sign in, or
            when you sync bCourses students.
          </p>
          <Form.Group className="mb-3" controlId="merge-old-email">
            <Form.Label>Old email</Form.Label>
            <Form.Control
              type="email"
              required
              value={oldEmail}
              onChange={(e) => setOldEmail(e.target.value)}
            />
          </Form.Group>
          <Form.Group controlId="merge-new-email">
            <Form.Label>New email</Form.Label>
            <Form.Control
              type="email"
              required
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
            />
          </Form.Group>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" type="submit" disabled={merging}>
            {merging ? "Merging…" : "Merge"}
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  );
}
