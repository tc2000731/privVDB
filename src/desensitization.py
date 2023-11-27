from collections import Counter
from tqdm import tqdm
import time
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances, manhattan_distances
from spacy.lang.en import English
from scipy.special import softmax
import math
import numpy as np
import logging
import random
import unicodedata
import pickle
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(process)d \n\t %(" "message)s",
    filename="log/trade2.log",
)


def word_normalize(text):
    """Resolve different type of unicode encodings."""
    return unicodedata.normalize('NFD', text)


def get_vocab(embedding_type, dataset):
    vocab = Counter()
    if embedding_type == "glove":
        tokenizer = English()
        tokenizer_type = "word"
    # else:
    #     tokenizer = BertTokenizer.from_pretrained(self.bert_model_path)
    #     tokenizer_type = "subword"

    num_line = sum(1 for _ in open(dataset))
    num_line /= 3
    with open(dataset, "r") as f:
        next(f)
        cnt = 0
        for line in tqdm(f, total=num_line-1):
            cnt += 1
            if cnt > num_line:
                break
            text = line.strip()
            if tokenizer_type == "subword":
                tokenized_text = tokenizer.tokenize(text)
            elif tokenizer_type == "word":
                tokenized_text = [token.text for token in tokenizer(text)]
            for token in tokenized_text:
                vocab[token] += 1
    return vocab


def get_embeddings(embedding_type, word2id, id2word):
    embeddings = {}
    if embedding_type == "glove":
        word_embedding_path = r"D:\Codes\pjlab\vdb\dpnlp\SanText\data\glove.840B.300d.txt"
        num_lines = sum(1 for _ in open(
            word_embedding_path, encoding='utf-8'))
        logging.info("Loading Word Embedding File: %s" %
                     word_embedding_path)

        with open(word_embedding_path, encoding='utf-8') as f:
            # Skip first line if of form count/dim.
            line = f.readline().rstrip().split(' ')
            if len(line) != 2:
                f.seek(0)
            for row in tqdm(f, total=num_lines - 1):
                content = row.rstrip().split(' ')
                cur_word = word_normalize(content[0])
                if cur_word in word2id.keys():
                    emb = [float(i) for i in content[1:]]
                    embeddings[word2id[cur_word]] = emb
    elif embedding_type == "bert":
        pass

    ret = []
    for i in range(len(word2id.keys())):
        try:
            ret.append(embeddings[i])
        except:
            ret.append(np.random.normal(0, 0.1, size=(300)))
            logging.error("embeddings not found " + str(i)+" " + id2word[i])
    return ret


def get_prob_matrix(embed_A, embed_B, eps):
    distance = euclidean_distances(embed_A, embed_B)
    logging.info("Matrix_Shape: "+str(distance.shape))
    sim_matrix = -distance
    prob_matrix = softmax(eps * sim_matrix / 2, axis=1)
    return prob_matrix


def get_prob_matrix_2(embed_A, embed_B, eps):
    n = len(embed_A)
    m = len(embed_B)
    distance = euclidean_distances(embed_A[:m], embed_B)

    # prob_matrix = np.ndarray((m, m), np.longdouble)
    # for i in range(len(word_embed_2)):
    #     for j in range(len(word_embed_1)):
    #         prob_matrix[j][i] = np.exp(-epsilon *
    #                                    distance[j][i], dtype=np.longdouble)
    prob_matrix = np.exp(-distance*eps)

    # for j in range(len(word_embed_2)):
    #     i = sid2wid[j]
    #     prob_matrix[i][j] = 1+prob_matrix[i][j]-np.sum(prob_matrix[i])

    b = np.ones(m)
    x = np.linalg.solve(prob_matrix, b)
    pickle.dump({"A": prob_matrix, "x": x}, open("log/Ax.pkl", "wb+"))
    logging.info(list(np.where(x < 0)))
    full_matrix = euclidean_distances(embed_A, embed_B)
    full_matrix = np.exp(-full_matrix*eps, dtype=np.longdouble)*x
    row_sum = np.sum(full_matrix, axis=1, keepdims=True)
    logging.info(row_sum)
    result = np.divide(full_matrix, row_sum)
    return result


class SanText:

    def __init__(self, config):

        self.base_dataset = config["base_dataset_path"]
        self.embedding_type = config["embedding_type"]
        self.non_sensitive_p = config["non_sensitive_p"]
        self.sensitive_word_percentage = config["sensitive_word_percentage"]
        self.epsilons = sorted(config["epsilons"])
        self.dP_mech = config["DP_mech"]
        self.init()

    def init(self):

        vocab = get_vocab(self.embedding_type, self.base_dataset)
        if self.embedding_type == "glove":
            self.tokenizer = English()
            self.tokenizer_type = "word"
        sensitive_word_count = int(
            math.ceil(self.sensitive_word_percentage * len(vocab)))
        words = [key for key, _ in vocab.most_common()]
        words = list(reversed(words))
        self.sensitive_words = set(words[:sensitive_word_count])

        self.word2id = {word: k for k, word in enumerate(words)}
        self.id2word = {k: word for k, word in enumerate(words)}
        self.words = set(words)
        word_embeddings = get_embeddings(
            self.embedding_type, self.word2id, self.id2word)
        self.prob_matrix = {}
        for e in self.epsilons:
            logging.info("Calculating matrix for eps = "+str(e))
            if self.dP_mech == "base":
                self.prob_matrix[e] = get_prob_matrix(
                    word_embeddings, word_embeddings[:sensitive_word_count], e)
            elif self.dP_mech == "adv":
                self.prob_matrix[e] = get_prob_matrix_2(
                    word_embeddings, word_embeddings[:sensitive_word_count], e)

    def desensitization(self, text, eps):
        if eps not in self.prob_matrix.keys():
            raise ValueError("eps not valid")
        pm = self.prob_matrix[eps]
        if self.embedding_type == "glove":
            doc = [token.text for token in self.tokenizer(text)]
            new_doc = []
            for word in doc:
                if word in self.sensitive_words:
                    index = self.word2id[word]
                    selected_index = np.random.choice(
                        len(pm[index]), 1, p=pm[index])[0]
                    new_doc.append(self.id2word[selected_index])
                else:
                    logging.info(word + " not in Sensitive_words")
                    flip_p = random.random()
                    if flip_p > self.non_sensitive_p:
                        new_doc.append(word)
                    elif word not in self.words:
                        logging.warn(word+" not in vocabulary!")
                        new_doc.append(word)
                    else:
                        index = self.word2id[word]
                        selected_index = np.random.choice(
                            len(pm[index]), 1, p=pm[index])[0]
                        new_doc.append(self.id2word[selected_index])
        return " ".join(new_doc)


if __name__ == "__main__":
    config = {
        "base_dataset_path": """D:\Codes\pjlab\\vdb\privVDB\\v0.1\privDB\data\CBTest\data\cbt_train.txt""",
        "embedding_type": "glove",
        "non_sensitive_p": 0.2,
        "sensitive_word_percentage": 0.95,
        "epsilons": [1],
        "DP_mech": "adv"
    }
    my_santext = SanText(config=config)
    o = "Assistants API and tools (retrieval, code interpreter) make it easy for developers to build AI assistants within their own applications. Each assistant incurs its own retrieval file storage fee based on the files passed to that assistant. The retrieval tool chunks and indexes your files content in our vector database."
    t = my_santext.desensitization(o, eps=config["epsilons"][0])
    save_path = "log/res.txt"
    print(t)
    open(save_path, "a+").write(str(config)+":\n"+o+'\n'+t+'\n')
