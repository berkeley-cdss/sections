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
        WARNING: This action will delete all attendance history, sessions,
        sections, and users associated with your course. This is
        irreversible and should only be done in order to prepare sections tool
        for a new semester. Be extremely cautious when using this button. You
        have been warned.
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
