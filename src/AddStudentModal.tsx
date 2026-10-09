import { useState } from "react";
import Button from "react-bootstrap/Button";
import FormControl from "react-bootstrap/FormControl";
import Modal from "react-bootstrap/Modal";

type Props = {
  show: boolean;
  onAdd: (emails: string) => Promise<void>;
  onClose: () => void;
  title?: string;
  warningText?: string;
};

export default function AddStudentModal({
  show,
  onAdd,
  onClose,
  title = "Add Student(s)",
  warningText = "Adding students to a new lab/discussion/tutoring section will automatically drop them from their current lab/discussion/tutoring section.",
}: Props) {
  const [email, setEmail] = useState("");
  // Clear the input whenever the modal closes.
  const [prevShow, setPrevShow] = useState(show);
  if (show !== prevShow) {
    setPrevShow(show);
    if (!show) {
      setEmail("");
    }
  }

  return (
    <Modal show={show} onHide={onClose}>
      <Modal.Header closeButton>
        <Modal.Title>{title}</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {warningText ? (
          <div className="alert alert-warning" role="alert">
            {warningText}
          </div>
        ) : null}
        <FormControl
          placeholder="Student(s) Email Address (comma-separated)"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
        <Button variant="primary" onClick={() => onAdd(email).then(onClose)}>
          {title}
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
