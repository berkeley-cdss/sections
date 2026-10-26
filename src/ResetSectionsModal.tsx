import Button from "react-bootstrap/Button";
import Modal from "react-bootstrap/Modal";

type Props = {
  show: boolean;
  onReset: () => Promise<void>;
  onClose: () => void;
};

export default function ResetSectionsModal({ show, onReset, onClose }: Props) {
  return (
    <Modal show={show} onHide={onClose}>
      <Modal.Header closeButton>
        <Modal.Title>Reset Sections Tool</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        WARNING: This action will delete all of your course's sections, their
        sessions and attendance history, and every student and staff assignment
        to them. Students and staff stay in the course. This is
        irreversible and does not need to be done after a semester ends. Consider
        carefully if you really need to press this button. You have been warned.
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
        <Button variant="danger" onClick={() => onReset().then(onClose)}>
          I understand. Reset!
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
